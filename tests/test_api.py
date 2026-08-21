from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import create_app
from app.models import InternalAccount
from app.services.store import RedisStore


async def seed_pool(store: RedisStore, now: int) -> None:
    item = InternalAccount(
        id="acc_opaque-test-id",
        username="person.one@example.invalid",
        password="synthetic-secret-one",
        region="US",
        status="active",
        last_synced_at=now,
        features=["shadowrocket_purchased"],
    )
    await store.replace_source_slice("source_a", now, [item])


@pytest.mark.asyncio
async def test_verify_ticket_reveal_and_replay_with_public_contract(redis_client, settings, monkeypatch) -> None:
    now = 1_800_000_000
    monkeypatch.setattr("app.api.time.time", lambda: now)
    store = RedisStore(redis_client, settings)
    await seed_pool(store, now)
    app = create_app(settings=settings, redis_client=redis_client, start_pollers=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver") as client:
        verify = await client.post(
            "/api/v2/session/verify",
            headers={"X-CSRF-Token": "1"},
            json={"token": "explicit-local-token"},
        )
        assert verify.status_code == 204
        cookie = verify.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=strict" in cookie

        ticket_response = await client.post("/api/v2/reveal-ticket", headers={"X-CSRF-Token": "1"})
        assert ticket_response.status_code == 200
        ticket = ticket_response.json()["ticket"]

        reveal = await client.post(
            "/api/v2/accounts/reveal",
            headers={"X-CSRF-Token": "1"},
            json={"ticket": ticket},
        )
        assert reveal.status_code == 200
        payload = reveal.json()
        assert payload["total"] == 1
        assert payload["exhausted"] is False
        assert payload["purchase_link"] is None
        assert len(payload["accounts"]) == 1
        selected_id = payload["accounts"][0]["id"]
        session_digest = await store.session_digest_if_valid(
            client.cookies.get(settings.cookie_name)
        )
        assert session_digest is not None
        assert await redis_client.sismember(
            store._key("session-shown", session_digest), selected_id
        )
        assert set(payload["accounts"][0]) == {
            "id", "username", "password", "region", "status", "last_synced_at", "features"
        }
        serialized = reveal.text.lower()
        for forbidden in ("source", "url", "status_text", "last_check", "raw"):
            assert forbidden not in serialized

        replay = await client.post(
            "/api/v2/accounts/reveal",
            headers={"X-CSRF-Token": "1"},
            json={"ticket": ticket},
        )
        assert replay.status_code == 403
        assert replay.json() == {"error": {"code": "access_denied", "message": "请求无法完成"}}


@pytest.mark.asyncio
async def test_reveal_always_returns_configured_store_link(redis_client, settings, monkeypatch) -> None:
    now = 1_800_000_000
    monkeypatch.setattr("app.api.time.time", lambda: now)
    configured = settings.with_overrides(store_url="https://store.example.invalid/account")
    store = RedisStore(redis_client, configured)
    await seed_pool(store, now)
    app = create_app(settings=configured, redis_client=redis_client, start_pollers=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver") as client:
        assert (
            await client.post(
                "/api/v2/session/verify",
                headers={"X-CSRF-Token": "1"},
                json={"token": "explicit-local-token"},
            )
        ).status_code == 204
        ticket = (
            await client.post("/api/v2/reveal-ticket", headers={"X-CSRF-Token": "1"})
        ).json()["ticket"]
        reveal = await client.post(
            "/api/v2/accounts/reveal",
            headers={"X-CSRF-Token": "1"},
            json={"ticket": ticket},
        )
        assert reveal.status_code == 200
        assert reveal.json()["exhausted"] is False
        assert reveal.json()["purchase_link"] == "https://store.example.invalid/account"


@pytest.mark.asyncio
async def test_headers_default_deny_cors_no_v1_and_no_store(redis_client, settings) -> None:
    app = create_app(settings=settings, redis_client=redis_client, start_pollers=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver") as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store, max-age=0"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["x-robots-tag"].startswith("noindex")
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert "access-control-allow-origin" not in response.headers
        assert (await client.get("/api/v1/accounts")).status_code == 404
        assert (await client.get("/docs")).status_code == 404


@pytest.mark.asyncio
async def test_readiness_and_reveal_fail_closed_when_pool_stale(redis_client, settings, monkeypatch) -> None:
    seeded_at = 1_800_000_000
    monkeypatch.setattr("app.api.time.time", lambda: seeded_at)
    stale_settings = settings.with_overrides(
        source_freshness_seconds=10,
        source_slice_ttl_seconds=60,
    )
    store = RedisStore(redis_client, stale_settings)
    await seed_pool(store, seeded_at)
    app = create_app(settings=stale_settings, redis_client=redis_client, start_pollers=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver") as client:
        assert (await client.get("/readyz")).status_code == 200
        await client.post(
            "/api/v2/session/verify",
            headers={"X-CSRF-Token": "1"},
            json={"token": "explicit-local-token"},
        )
        ticket = (await client.post("/api/v2/reveal-ticket", headers={"X-CSRF-Token": "1"})).json()["ticket"]

        monkeypatch.setattr("app.api.time.time", lambda: seeded_at + 15)
        monkeypatch.setattr("app.services.store.time.time", lambda: seeded_at + 15)
        assert (await client.get("/readyz")).status_code == 503
        reveal = await client.post(
            "/api/v2/accounts/reveal",
            headers={"X-CSRF-Token": "1"},
            json={"ticket": ticket},
        )
        assert reveal.status_code == 200
        assert reveal.json()["exhausted"] is True
        assert reveal.json()["accounts"] == []

        monkeypatch.setattr("app.api.time.time", lambda: seeded_at)
        monkeypatch.setattr("app.services.store.time.time", lambda: seeded_at)
        replay_after_recovery = await client.post(
            "/api/v2/accounts/reveal",
            headers={"X-CSRF-Token": "1"},
            json={"ticket": ticket},
        )
        assert replay_after_recovery.status_code == 403


@pytest.mark.asyncio
async def test_cross_site_origin_and_fetch_metadata_are_rejected(redis_client, settings) -> None:
    protected = settings.with_overrides(public_origin="https://share.example.invalid")
    app = create_app(settings=protected, redis_client=redis_client, start_pollers=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver") as client:
        cross_origin = await client.post(
            "/api/v2/session/verify",
            headers={"X-CSRF-Token": "1", "Origin": "https://evil.example.invalid"},
            json={"token": "explicit-local-token"},
        )
        cross_site = await client.post(
            "/api/v2/session/verify",
            headers={
                "X-CSRF-Token": "1",
                "Origin": "https://share.example.invalid",
                "Sec-Fetch-Site": "cross-site",
            },
            json={"token": "explicit-local-token"},
        )
        same_origin = await client.post(
            "/api/v2/session/verify",
            headers={
                "X-CSRF-Token": "1",
                "Origin": "https://share.example.invalid",
                "Sec-Fetch-Site": "same-origin",
            },
            json={"token": "explicit-local-token"},
        )
        assert cross_origin.status_code == 403
        assert cross_site.status_code == 403
        assert same_origin.status_code == 204


@pytest.mark.asyncio
async def test_ticket_recovers_when_tls_proxy_drops_the_first_secure_cookie(redis_client, settings) -> None:
    protected = settings.with_overrides(
        public_origin="https://share.example.invalid",
        cookie_secure=True,
    )
    app = create_app(settings=protected, redis_client=redis_client, start_pollers=False)
    headers = {
        "X-CSRF-Token": "1",
        "Origin": "https://share.example.invalid",
        "Sec-Fetch-Site": "same-origin",
    }
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://upstream.internal",
    ) as client:
        verify = await client.post(
            "/api/v2/session/verify",
            headers={**headers, "X-Forwarded-Proto": "https"},
            json={"token": "explicit-local-token"},
        )
        assert verify.status_code == 204
        first_cookie = verify.headers.get("set-cookie", "")
        assert "Secure" in first_cookie and "HttpOnly" in first_cookie

        ticket = await client.post("/api/v2/reveal-ticket", headers=headers)
        assert ticket.status_code == 200
        replacement_cookie = ticket.headers.get("set-cookie", "")
        assert "Secure" in replacement_cookie and "HttpOnly" in replacement_cookie
        replacement_token = client.cookies.get(protected.cookie_name)
        assert replacement_token is not None

        client.cookies.set(
            protected.cookie_name,
            replacement_token,
            domain="upstream.internal",
            path="/",
        )
        next_ticket = await client.post("/api/v2/reveal-ticket", headers=headers)
        assert next_ticket.status_code == 200


@pytest.mark.asyncio
async def test_session_rate_limit_returns_generic_429(redis_client, settings, monkeypatch) -> None:
    limited = settings.with_overrides(rate_ticket_session_limit=1)
    now = 1_800_000_000
    monkeypatch.setattr("app.api.time.time", lambda: now)
    app = create_app(settings=limited, redis_client=redis_client, start_pollers=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver") as client:
        verify = await client.post(
            "/api/v2/session/verify",
            headers={"X-CSRF-Token": "1"},
            json={"token": "explicit-local-token"},
        )
        assert verify.status_code == 204

        first = await client.post("/api/v2/reveal-ticket", headers={"X-CSRF-Token": "1"})
        second = await client.post("/api/v2/reveal-ticket", headers={"X-CSRF-Token": "1"})
        assert first.status_code == 200
        assert second.status_code == 429
        assert second.json() == {"error": {"code": "rate_limited", "message": "请求过于频繁"}}
