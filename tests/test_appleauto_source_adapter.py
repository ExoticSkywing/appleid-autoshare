from __future__ import annotations

import httpx
import pytest

from app.adapters.appleauto_source import AppleAutoSourceAdapter


@pytest.mark.asyncio
async def test_appleauto_fetch_accounts() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/client/getAllAccounts")
        assert request.headers["x-api-key"] == "test-key"
        return httpx.Response(
            200,
            json=[
                {
                    "id": 1,
                    "username": "self_hosted@example.com",
                    "password": "pwd-1",
                    "last_check_success": True,
                    "region_display": "US",
                }
            ],
        )

    adapter = AppleAutoSourceAdapter(
        alias="appleauto",
        url="https://mock.appleauto.local",
        api_key="test-key",
        timeout_seconds=5.0,
        max_response_bytes=100000,
        unhealthy_markers=("已锁定",),
        transport=httpx.MockTransport(handler),
    )
    accounts = await adapter.fetch_accounts()
    assert len(accounts) == 1
    acc = accounts[0]
    assert acc.username == "self_hosted@example.com"
    assert "source_appleauto" in acc.features
    assert "shadowrocket_purchased" in acc.features
    assert "appleauto_id_1" in acc.features


@pytest.mark.asyncio
async def test_appleauto_restart_account() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/client/restartAccount")
        assert request.headers["x-api-key"] == "test-key"
        return httpx.Response(200, json={"ret": 1, "msg": "success"})

    adapter = AppleAutoSourceAdapter(
        alias="appleauto",
        url="https://mock.appleauto.local",
        api_key="test-key",
        timeout_seconds=5.0,
        max_response_bytes=100000,
        unhealthy_markers=("已锁定",),
        transport=httpx.MockTransport(handler),
    )
    ok = await adapter.restart_account(1)
    assert ok is True
