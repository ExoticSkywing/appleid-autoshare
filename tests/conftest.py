from __future__ import annotations

import fakeredis.aioredis
import pytest

from app.config import Settings


@pytest.fixture
def settings() -> Settings:
    configured = Settings(
        environment="test",
        redis_url="redis://unused:6379/0",
        id_hmac_secret="id-secret-for-tests-only-000000000000",
        state_hmac_secret="state-secret-for-tests-only-000000000",
        turnstile_test_mode=True,
        turnstile_test_token="explicit-local-token",
        cookie_secure=False,
        start_pollers=False,
        rate_verify_ip_limit=20,
        rate_ticket_ip_limit=20,
        rate_ticket_session_limit=20,
        rate_reveal_ip_limit=20,
        rate_reveal_session_limit=20,
    ).validated()
    object.__setattr__(configured, "cookie_name", "aid_session")
    return configured


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()
