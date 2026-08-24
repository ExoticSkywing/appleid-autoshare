from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from app.adapters.ikuuu_source import IkuuuSourceAdapter, IkuuuSourceError
from app.services.aggregator import AccountAggregator

NOW = int(datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc).timestamp())
URL = "https://api.example.invalid/user/get-appleid"
REFERER = "https://api.example.invalid/user/tutorial?os=ios&client=synthetic"
COOKIE = "session=opaque-synthetic-cookie"


def payload(*, expire_time: int = NOW + 900) -> dict[str, object]:
    return {
        "ret": 1,
        "msg": "synthetic success",
        "data": {
            "ios_apple_id": "reserve@example.invalid",
            "ios_apple_id_password": "synthetic-password",
            "expire_time": expire_time,
        },
    }


def adapter(handler, *, cookie: str = COOKIE) -> IkuuuSourceAdapter:
    return IkuuuSourceAdapter(
        alias="reserve_d",
        url=URL,
        cookie=cookie,
        referer=REFERER,
        timeout_seconds=1,
        max_response_bytes=4096,
        unhealthy_markers=(),
        now=lambda: NOW,
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_valid_response_uses_secret_headers_and_parses_expiry() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["cookie"] == COOKIE
        assert request.headers["referer"] == REFERER
        assert request.headers["x-requested-with"] == "XMLHttpRequest"
        return httpx.Response(200, headers={"content-type": "application/json; charset=utf-8"}, json=payload())

    records = await adapter(handler).fetch_accounts()

    assert len(records) == 1
    assert records[0].username == "reserve@example.invalid"
    assert records[0].password == "synthetic-password"
    assert records[0].source_valid_until == NOW + 900


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_http_auth_failures_are_classified_without_secret_leak(status: int) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=COOKIE)

    with pytest.raises(IkuuuSourceError, match="auth_expired") as caught:
        await adapter(handler).fetch_accounts()
    assert caught.value.reason == "auth_expired"
    assert COOKIE not in repr(caught.value)


@pytest.mark.asyncio
async def test_ret_failure_is_auth_expired() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/json"}, json={"ret": 0, "msg": COOKIE, "data": None})

    with pytest.raises(IkuuuSourceError) as caught:
        await adapter(handler).fetch_accounts()
    assert caught.value.reason == "auth_expired"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, headers={"content-type": "image/png"}, content=b"not-json"),
        httpx.Response(200, headers={"content-type": "application/json"}, content=b"not-json"),
        httpx.Response(200, headers={"content-type": "application/json"}, json={"ret": 1, "msg": "ok", "data": {}}),
        httpx.Response(200, headers={"content-type": "application/json"}, json=payload(expire_time=NOW)),
        httpx.Response(200, headers={"content-type": "application/json"}, json=payload(expire_time=NOW + 367 * 86400)),
    ],
)
async def test_schema_and_expiry_drift_are_separate_from_auth(response: httpx.Response) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return response

    with pytest.raises(IkuuuSourceError) as caught:
        await adapter(handler).fetch_accounts()
    assert caught.value.reason == "schema_drift"


@pytest.mark.asyncio
async def test_json_body_with_legacy_text_html_content_type_is_accepted() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, json=payload())

    records = await adapter(handler).fetch_accounts()
    assert len(records) == 1


@pytest.mark.asyncio
async def test_timeout_is_network_failed() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("synthetic timeout")

    with pytest.raises(IkuuuSourceError) as caught:
        await adapter(handler).fetch_accounts()
    assert caught.value.reason == "network_failed"


def test_repr_does_not_disclose_runtime_secrets() -> None:
    instance = adapter(lambda _request: httpx.Response(500))
    rendered = repr(instance)
    assert COOKIE not in rendered
    assert "api.example.invalid" not in rendered


def test_adapter_rejects_plain_http_and_cross_origin_before_request() -> None:
    for url, referer in (
        ("http://api.example.invalid/accounts", REFERER),
        (URL, "http://api.example.invalid/tutorial"),
        (URL, "https://other.example.invalid/tutorial"),
        ("https://user:pass@api.example.invalid/accounts", REFERER),
    ):
        with pytest.raises(ValueError, match="invalid authenticated source"):
            IkuuuSourceAdapter(
                alias="reserve_d",
                url=url,
                cookie=COOKIE,
                referer=referer,
                timeout_seconds=1,
                max_response_bytes=4096,
                unhealthy_markers=(),
            )


def test_password_is_treated_as_opaque_credential() -> None:
    raw = " synthetic-password-with-spaces "
    instance = adapter(lambda _request: httpx.Response(500))
    records = instance.parse_response(
        httpx.Response(200, json={
            "ret": 1,
            "data": {
                "ios_apple_id": "reserve@example.invalid",
                "ios_apple_id_password": raw,
                "expire_time": NOW + 900,
            },
        }).content
    )
    assert records[0].password == raw


@pytest.mark.asyncio
async def test_aggregator_logs_only_fixed_reason_and_does_not_renew_slice(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "opaque-never-log-this"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, headers={"content-type": "application/json"})

    configured = adapter(handler, cookie=secret)

    class Store:
        async def replace_source_slice(self, *args, **kwargs):
            raise AssertionError("failed poll must not write")

    aggregator = AccountAggregator(store=Store(), adapters=[], id_secret="synthetic")  # type: ignore[arg-type]
    with caplog.at_level("WARNING"):
        assert await aggregator.poll_once(configured) is False
    assert "result=auth_expired" in caplog.text
    assert secret not in caplog.text
    assert "api.example.invalid" not in caplog.text
