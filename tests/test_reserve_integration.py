from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.api import _build_aggregator
from app.config import ConfigurationError, Settings
from app.models import InternalAccount
from app.services.store import RedisStore


def account(username: str, synced: int) -> InternalAccount:
    return InternalAccount(
        id=f"acc_{synced}",
        username=username,
        password="synthetic-password",
        region="Unknown",
        last_synced_at=synced,
        features=[],
        upstream_updated_at=synced,
    )


def test_reserve_settings_repr_redacts_endpoint_and_cookie(settings: Settings) -> None:
    endpoint = "https://reserve.example.invalid/private"
    secret = "opaque-synthetic-session"
    configured = settings.with_overrides(
        source_c_enabled=True,
        source_c_url=endpoint,
        source_c_cookie=secret,
    )
    rendered = repr(configured)
    assert endpoint not in rendered
    assert secret not in rendered


def test_reserve_configuration_is_optional_but_fail_fast_when_enabled(settings: Settings) -> None:
    settings.with_overrides(source_c_enabled=False, source_c_url="", source_c_cookie="")
    with pytest.raises(ConfigurationError, match="SOURCE_C_URL"):
        settings.with_overrides(source_c_enabled=True, source_c_url="", source_c_cookie="synthetic")
    with pytest.raises(ConfigurationError, match="SOURCE_C_COOKIE"):
        settings.with_overrides(
            source_c_enabled=True,
            source_c_url="https://reserve.example.invalid/private",
            source_c_cookie="",
        )
    with pytest.raises(ConfigurationError):
        settings.with_overrides(
            source_c_enabled=True,
            source_c_url="http://reserve.example.invalid/private",
            source_c_cookie="synthetic",
        )

def test_disabled_reserve_ignores_stale_invalid_reserve_parameters(settings: Settings) -> None:
    configured = settings.with_overrides(
        source_c_enabled=False,
        source_c_sample_count=99,
        source_c_timezone="Invalid/Timezone",
    )
    assert configured.source_c_enabled is False


def test_reserve_configuration_ranges_and_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    env = {
        "APP_ENV": "test",
        "START_POLLERS": "false",
        "TURNSTILE_TEST_MODE": "true",
        "TURNSTILE_TEST_TOKEN": "explicit-local-token",
        "SOURCE_C_ENABLED": "true",
        "SOURCE_C_URL": "https://reserve.example.invalid/private",
        "SOURCE_C_COOKIE": "opaque-synthetic-session",
        "SOURCE_C_POLL_SECONDS": "300",
        "SOURCE_C_SAMPLE_COUNT": "4",
        "SOURCE_C_SAMPLE_JITTER_MIN_MS": "10",
        "SOURCE_C_SAMPLE_JITTER_MAX_MS": "20",
        "SOURCE_C_FRESHNESS_SECONDS": "600",
        "SOURCE_C_UPSTREAM_MAX_AGE_SECONDS": "900",
        "SOURCE_C_SLICE_TTL_SECONDS": "1200",
        "SOURCE_C_TIMEZONE": "UTC",
        "SOURCE_C_AUTH_FAILURE_ALERT_THRESHOLD": "3",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    configured = Settings.from_env()
    assert configured.source_c_sample_count == 4
    assert configured.source_c_sample_jitter_ms == (10, 20)
    assert configured.source_c_freshness_seconds == 600
    with pytest.raises(ConfigurationError):
        configured.with_overrides(source_c_sample_count=6)
    with pytest.raises(ConfigurationError):
        configured.with_overrides(source_c_slice_ttl_seconds=600)


def test_builder_registers_reserve_only_when_enabled(settings: Settings) -> None:
    disabled = _build_aggregator(settings, store=None)  # type: ignore[arg-type]
    assert [adapter.alias for adapter, _ in disabled.adapters] == ["source_a", "source_b"]

    enabled_settings = settings.with_overrides(
        source_c_enabled=True,
        source_c_url="https://reserve.example.invalid/private",
        source_c_cookie="opaque-synthetic-session",
    )
    enabled = _build_aggregator(enabled_settings, store=None)  # type: ignore[arg-type]
    assert [adapter.alias for adapter, _ in enabled.adapters] == ["source_a", "source_b", "reserve_c"]

    both_settings = enabled_settings.with_overrides(
        source_d_enabled=True,
        source_d_url="https://api.example.invalid/private",
        source_d_cookie="opaque-synthetic-session-d",
        source_d_referer="https://api.example.invalid/tutorial",
    )
    both = _build_aggregator(both_settings, store=None)  # type: ignore[arg-type]
    assert [adapter.alias for adapter, _ in both.adapters] == [
        "source_a",
        "source_b",
        "reserve_c",
        "reserve_d",
    ]


@pytest.mark.asyncio
async def test_reserve_slice_has_independent_freshness_ttl_and_upstream_age(redis_client, settings) -> None:
    configured = settings.with_overrides(
        source_c_enabled=True,
        source_c_url="https://reserve.example.invalid/private",
        source_c_cookie="opaque-synthetic-session",
        source_c_freshness_seconds=600,
        source_c_slice_ttl_seconds=1200,
        source_c_upstream_max_age_seconds=900,
    )
    store = RedisStore(redis_client, configured)
    fetched = int(datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc).timestamp())
    await store.replace_source_slice("reserve_c", fetched, [account("reserve@example.invalid", fetched - 100)])
    await store.replace_source_slice("source_a", fetched + 601, [account("primary@example.invalid", fetched + 601)])

    assert await store.get_fresh_source_slice("reserve_c", now=fetched + 600) is None

    # A newer primary slice remains independently serviceable even after the
    # reserve slice expires.
    primary_only = await store.get_fresh_pool(now=fetched + 601)
    assert primary_only is not None
    assert [item.username for item in primary_only.accounts] == ["primary@example.invalid"]

    stale_upstream_store = RedisStore(redis_client, configured)
    await stale_upstream_store.replace_source_slice(
        "reserve_c",
        fetched + 700,
        [account("old-upstream@example.invalid", fetched - 201)],
    )
    # Add a currently fresh primary record so the aggregate is non-empty while
    # proving that the stale reserve record itself is excluded.
    await stale_upstream_store.replace_source_slice(
        "source_a",
        fetched + 700,
        [account("current-primary@example.invalid", fetched + 700)],
    )
    pool = await stale_upstream_store.get_fresh_pool(now=fetched + 700)
    assert pool is not None
    assert "old-upstream@example.invalid" not in {item.username for item in pool.accounts}
