from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.services.turnstile import TurnstileVerifier


@pytest.mark.asyncio
async def test_turnstile_requires_success_expected_action_and_hostname(settings: Settings) -> None:
    responses = iter(
        [
            {"success": True, "action": "reveal", "hostname": "share.example.invalid"},
            {"success": True, "action": "wrong", "hostname": "share.example.invalid"},
            {"success": True, "action": "reveal", "hostname": "other.example.invalid"},
            {"success": False, "error-codes": ["secret-input-response"]},
        ]
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(responses))

    production_like = Settings(
        environment="test",
        redis_url=settings.redis_url,
        id_hmac_secret=settings.id_hmac_secret,
        state_hmac_secret=settings.state_hmac_secret,
        turnstile_test_mode=False,
        turnstile_secret_key="synthetic-turnstile-secret",
        turnstile_verify_url="https://turnstile.invalid/verify",
        turnstile_expected_action="reveal",
        turnstile_expected_hostname="share.example.invalid",
        start_pollers=False,
    ).validated()
    verifier = TurnstileVerifier(production_like, transport=httpx.MockTransport(handler))

    assert await verifier.verify("token", "203.0.113.10") is True
    assert await verifier.verify("token", "203.0.113.10") is False
    assert await verifier.verify("token", "203.0.113.10") is False
    assert await verifier.verify("token", "203.0.113.10") is False


@pytest.mark.asyncio
async def test_turnstile_test_mode_is_explicit_and_exact(settings: Settings) -> None:
    verifier = TurnstileVerifier(settings)
    assert await verifier.verify("explicit-local-token", "127.0.0.1") is True
    assert await verifier.verify("anything-else", "127.0.0.1") is False
