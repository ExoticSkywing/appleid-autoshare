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
        "SOURCE_C_ENABLED": "true",
        "SOURCE_C_URL": "https://reserve.example.invalid/accounts",
        "SOURCE_C_COOKIE": "opaque-synthetic-cookie",
        "SOURCE_C_POLL_SECONDS": "301",
        "SOURCE_C_SAMPLE_COUNT": "4",
        "SOURCE_C_SAMPLE_JITTER_MIN_MS": "12",
        "SOURCE_C_SAMPLE_JITTER_MAX_MS": "34",
        "SOURCE_C_FRESHNESS_SECONDS": "601",
        "SOURCE_C_UPSTREAM_MAX_AGE_SECONDS": "901",
        "SOURCE_C_SLICE_TTL_SECONDS": "1201",
        "SOURCE_D_ENABLED": "true",
        "SOURCE_D_URL": "https://api.example.invalid/accounts",
        "SOURCE_D_COOKIE": "opaque-synthetic-cookie-d",
        "SOURCE_D_REFERER": "https://api.example.invalid/tutorial",
        "SOURCE_D_POLL_SECONDS": "302",
        "SOURCE_D_FRESHNESS_SECONDS": "303",
        "SOURCE_D_SLICE_TTL_SECONDS": "604",
        "SOURCE_QINGFENG_ENABLED": "true",
        "SOURCE_QINGFENG_URL": "https://feed.example.invalid/share/synthetic",
        "SOURCE_QINGFENG_REFERER": "https://portal.example.invalid/",
        "SOURCE_QINGFENG_POLL_SECONDS": "61",
        "SOURCE_QINGFENG_FRESHNESS_SECONDS": "91",
        "SOURCE_QINGFENG_SLICE_TTL_SECONDS": "181",
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
    assert settings.source_c_enabled is True
    assert settings.source_c_sample_count == 4
    assert settings.source_c_sample_jitter_ms == (12, 34)
    assert settings.source_c_freshness_seconds == 601
    assert settings.source_d_enabled is True
    assert settings.source_d_interval_seconds == 302
    assert settings.source_d_freshness_seconds == 303
    assert settings.source_qingfeng_enabled is True
    assert settings.source_qingfeng_interval_seconds == 61
    assert settings.source_qingfeng_freshness_seconds == 91
    assert settings.source_qingfeng_slice_ttl_seconds == 181
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


def test_turnstile_has_bounded_loading_and_recovery_contract() -> None:
    root = Path(__file__).parents[1]
    script = (root / "static" / "app.js").read_text(encoding="utf-8")
    markup = (root / "static" / "index.html").read_text(encoding="utf-8")

    assert "TURNSTILE_LOAD_TIMEOUT_MS = 12_000" in script
    assert "TURNSTILE_RETRY_LIMIT = 1" in script
    assert 'host.querySelector("iframe")' in script
    assert 'input[name="cf-turnstile-response"]' in script
    assert '"before-interactive-callback"' in script
    assert "MutationObserver" in script
    assert 'byId("credentialState").textContent = "等待你完成验证"' in script
    assert '"timeout-callback"' in script
    assert '"unsupported-callback"' in script
    assert "人机验证没有加载出来" in script
    assert "点击重新加载验证" in script
    assert 'id="turnstileLoading"' in markup
    assert 'id="verifyButton" class="primary-action gooey-action hidden"' in markup
    assert 'id="verifyActionHint"' not in markup


def test_novice_turnstile_is_gated_by_app_selection() -> None:
    root = Path(__file__).parents[1]
    script = (root / "static" / "app.js").read_text(encoding="utf-8")
    markup = (root / "static" / "index.html").read_text(encoding="utf-8")

    assert 'id="credential" class="credential hidden"' in markup
    assert 'id="safetyRule" class="safety-rule hidden"' in markup
    assert 'id="intentSummary" class="intent-summary hidden"' in markup
    assert "function startTurnstile()" in script
    assert "function stopTurnstile()" in script
    assert "function changeIntent()" in script
    select_intent = script.index("function selectIntent(intent)")
    start_turnstile = script.index("startTurnstile();", select_intent)
    next_function = script.index("function changeIntent()", select_intent)
    assert select_intent < start_turnstile < next_function


def test_login_result_uses_observable_account_page_evidence() -> None:
    root = Path(__file__).parents[1]
    script = (root / "static" / "app.js").read_text(encoding="utf-8")
    markup = (root / "static" / "index.html").read_text(encoding="utf-8")

    assert "App Store 是否同时显示账号昵称和 Apple ID？" in script
    assert "出现账号昵称和 Apple ID" in markup
    assert "两项同时出现，才表示登录成功" in markup
    assert "appstore-login-success-reference.jpg" in markup
    assert "已看到两项信息" in markup
    assert "没看到 / 不确定" in markup
    assert 'data-login-result="success"' in markup
    assert 'data-result="login_failed"' in markup
