from __future__ import annotations

import pytest

from app.config import ConfigurationError
from app.models import InternalAccount
from app.services.store import RedisStore


def account(account_id: str, username: str) -> InternalAccount:
    return InternalAccount(
        id=account_id,
        username=username,
        password="synthetic-password",
        region="Unknown",
        last_synced_at=100,
        features=[],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (
            "all",
            {
                "a@example.invalid",
                "b@example.invalid",
                "c@example.invalid",
                "d@example.invalid",
            },
        ),
        ("primary_only", {"a@example.invalid", "b@example.invalid"}),
        ("source_a_only", {"a@example.invalid"}),
        ("source_b_only", {"b@example.invalid"}),
        ("reserve_only", {"c@example.invalid"}),
        ("source_d_only", {"d@example.invalid"}),
        ("ikuuu_only", {"d@example.invalid"}),
    ],
)
async def test_delivery_source_mode_selects_only_configured_slices(redis_client, settings, mode, expected) -> None:
    configured = settings.with_overrides(
        source_c_enabled=True,
        source_c_url="https://reserve.example.invalid/private",
        source_c_cookie="opaque-synthetic-session",
        source_d_enabled=True,
        source_d_url="https://api.example.invalid/private",
        source_d_cookie="opaque-synthetic-session-d",
        source_d_referer="https://api.example.invalid/tutorial",
        delivery_source_mode=mode,
    )
    store = RedisStore(redis_client, configured)
    await store.replace_source_slice("source_a", 100, [account("acc_a", "a@example.invalid")])
    await store.replace_source_slice("source_b", 100, [account("acc_b", "b@example.invalid")])
    await store.replace_source_slice("reserve_c", 100, [account("acc_c", "c@example.invalid")])
    await store.replace_source_slice("reserve_d", 100, [account("acc_d", "d@example.invalid")])

    pool = await store.get_fresh_pool(now=100)

    assert pool is not None
    assert {item.username for item in pool.accounts} == expected


@pytest.mark.asyncio
async def test_reserve_only_never_falls_back_to_primary(redis_client, settings) -> None:
    configured = settings.with_overrides(
        source_c_enabled=True,
        source_c_url="https://reserve.example.invalid/private",
        source_c_cookie="opaque-synthetic-session",
        delivery_source_mode="reserve_only",
    )
    store = RedisStore(redis_client, configured)
    await store.replace_source_slice("source_a", 100, [account("acc_a", "a@example.invalid")])
    await store.replace_source_slice("source_b", 100, [account("acc_b", "b@example.invalid")])

    assert await store.get_fresh_pool(now=100) is None


@pytest.mark.asyncio
async def test_source_d_only_never_falls_back_to_any_other_source(redis_client, settings) -> None:
    configured = settings.with_overrides(
        source_d_enabled=True,
        source_d_url="https://api.example.invalid/private",
        source_d_cookie="opaque-synthetic-session-d",
        source_d_referer="https://api.example.invalid/tutorial",
        delivery_source_mode="source_d_only",
    )
    store = RedisStore(redis_client, configured)
    await store.replace_source_slice("source_a", 100, [account("acc_a", "a@example.invalid")])
    await store.replace_source_slice("reserve_c", 100, [account("acc_c", "c@example.invalid")])

    assert await store.get_fresh_pool(now=100) is None


def test_source_d_referer_must_share_endpoint_origin(settings) -> None:
    with pytest.raises(ConfigurationError, match="same origin"):
        settings.with_overrides(
            source_d_enabled=True,
            source_d_url="https://api.example.invalid/private",
            source_d_cookie="opaque-synthetic-session-d",
            source_d_referer="https://other.example.invalid/tutorial",
        )


def test_delivery_mode_validation(settings) -> None:
    with pytest.raises(ConfigurationError, match="DELIVERY_SOURCE_MODE"):
        settings.with_overrides(delivery_source_mode="client_supplied")
    with pytest.raises(ConfigurationError, match="SOURCE_C_ENABLED"):
        settings.with_overrides(delivery_source_mode="reserve_only", source_c_enabled=False)
    with pytest.raises(ConfigurationError, match="SOURCE_D_ENABLED"):
        settings.with_overrides(delivery_source_mode="source_d_only", source_d_enabled=False)
