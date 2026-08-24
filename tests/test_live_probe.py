from __future__ import annotations

import importlib.util
from pathlib import Path

import httpx
import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "live_probe.py"
FIXTURE = Path(__file__).parent / "fixtures" / "reserve_source" / "sample_one.html"


@pytest.mark.asyncio
async def test_live_probe_is_redacted_with_mock_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = importlib.util.spec_from_file_location("live_probe", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    secret = "opaque-probe-secret"
    monkeypatch.setenv("SOURCE_C_URL", "https://reserve.example.invalid/accounts")
    monkeypatch.setenv("SOURCE_C_COOKIE", secret)
    monkeypatch.setenv("SOURCE_C_SAMPLE_COUNT", "1")
    monkeypatch.setenv("SOURCE_C_SAMPLE_JITTER_MIN_MS", "0")
    monkeypatch.setenv("SOURCE_C_SAMPLE_JITTER_MAX_MS", "0")
    monkeypatch.setenv("SOURCE_C_TIMEZONE", "UTC")
    monkeypatch.setenv("SOURCE_C_UPSTREAM_MAX_AGE_SECONDS", "999999999")

    original = module.AuthenticatedDomSourceAdapter

    def mocked_adapter(**kwargs):
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["cookie"] == secret
            return httpx.Response(200, headers={"content-type": "text/html"}, content=FIXTURE.read_bytes())

        kwargs["transport"] = httpx.MockTransport(handler)
        return original(**kwargs)

    monkeypatch.setattr(module, "AuthenticatedDomSourceAdapter", mocked_adapter)
    result = await module.probe()
    rendered = str(result)
    assert result["classification"] == "ok"
    assert result["account_count"] == 1
    assert secret not in rendered
    assert "rotation.one@example.invalid" not in rendered
    assert set(result) == {"classification", "account_count", "max_source_age_seconds"}


@pytest.mark.asyncio
async def test_source_d_probe_is_redacted_and_has_no_stable_account_hash(monkeypatch) -> None:
    spec = importlib.util.spec_from_file_location("live_probe_d", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    secret = "opaque-probe-secret-d"
    monkeypatch.setenv("SOURCE_PROBE", "D")
    monkeypatch.setenv("SOURCE_D_URL", "https://api.example.invalid/accounts")
    monkeypatch.setenv("SOURCE_D_COOKIE", secret)
    monkeypatch.setenv("SOURCE_D_REFERER", "https://api.example.invalid/tutorial")
    original = module.IkuuuSourceAdapter

    def mocked_adapter(**kwargs):
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["cookie"] == secret
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                json={
                    "ret": 1,
                    "data": {
                        "ios_apple_id": "probe@example.invalid",
                        "ios_apple_id_password": "synthetic-password",
                        "expire_time": 2_000_000_900,
                    },
                },
            )

        kwargs["transport"] = httpx.MockTransport(handler)
        kwargs["now"] = lambda: 2_000_000_000
        return original(**kwargs)

    monkeypatch.setattr(module, "IkuuuSourceAdapter", mocked_adapter)
    result = await module.probe()
    rendered = str(result)
    assert result == {"classification": "ok", "account_count": 1}
    assert secret not in rendered
    assert "probe@example.invalid" not in rendered
