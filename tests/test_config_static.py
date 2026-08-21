from __future__ import annotations

from pathlib import Path

import pytest

from app.config import ConfigurationError, Settings


def test_production_rejects_test_mode_and_missing_required_configuration() -> None:
    with pytest.raises(ConfigurationError):
        Settings(environment="production", turnstile_test_mode=True).validated()
    with pytest.raises(ConfigurationError):
        Settings(environment="production", turnstile_test_mode=False).validated()


def test_pool_ttl_and_freshness_cannot_exceed_sixty_seconds(settings: Settings) -> None:
    with pytest.raises(ConfigurationError):
        settings.with_overrides(pool_ttl_seconds=61)
    with pytest.raises(ConfigurationError):
        settings.with_overrides(pool_freshness_seconds=61)


def test_environment_runtime_controls_are_not_silently_ignored(monkeypatch) -> None:
    values = {
        "APP_ENV": "development",
        "START_POLLERS": "false",
        "SOURCE_A_POLL_SECONDS": "31",
        "SOURCE_B_POLL_SECONDS": "37",
        "UPSTREAM_TIMEOUT_SECONDS": "9",
        "SOURCE_FRESHNESS_SECONDS": "42",
        "SOURCE_SLICE_TTL_SECONDS": "77",
        "POOL_TTL_SECONDS": "41",
        "POOL_FRESHNESS_SECONDS": "40",
        "SESSION_TTL_SECONDS": "321",
        "TICKET_TTL_SECONDS": "17",
        "RATE_WINDOW_SECONDS": "53",
        "COOKIE_NAME": "test-cookie",
        "PUBLIC_ORIGIN": "https://share.example.invalid",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    settings = Settings.from_env()
    assert settings.source_a_interval_seconds == 31
    assert settings.source_b_interval_seconds == 37
    assert settings.upstream_timeout_seconds == 9
    assert settings.source_freshness_seconds == 42
    assert settings.source_slice_ttl_seconds == 77
    assert settings.pool_ttl_seconds == 41
    assert settings.pool_freshness_seconds == 40
    assert settings.session_ttl_seconds == 321
    assert settings.ticket_ttl_seconds == 17
    assert settings.rate_window_seconds == 53
    assert settings.cookie_name == "test-cookie"
    assert settings.public_origin == "https://share.example.invalid"


def test_production_requires_origin_and_host_prefixed_cookie() -> None:
    base = Settings(
        environment="production",
        start_pollers=False,
        id_hmac_secret="i" * 32,
        state_hmac_secret="s" * 32,
        turnstile_site_key="site",
        turnstile_secret_key="secret",
        turnstile_expected_hostname="share.example.invalid",
        turnstile_expected_action="reveal",
        turnstile_verify_url="https://verify.example.invalid",
        turnstile_script_url="https://script.example.invalid/api.js",
    )
    with pytest.raises(ConfigurationError):
        base.validated()
    with pytest.raises(ConfigurationError):
        base.with_overrides(public_origin="https://share.example.invalid", cookie_name="plain")
    base.with_overrides(public_origin="https://share.example.invalid").validated()


def test_spa_uses_safe_dom_apis_and_has_no_ingestion_identifiers() -> None:
    script = (Path(__file__).parents[1] / "static" / "app.js").read_text(encoding="utf-8")
    assert "textContent" in script
    assert "innerHTML" not in script
    assert "source_a" not in script
    assert "source_b" not in script
    assert "data-clipboard-text" not in script
