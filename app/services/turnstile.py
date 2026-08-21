from __future__ import annotations

import hmac

import httpx

from app.config import Settings


class TurnstileVerifier:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport

    async def verify(self, token: str, remote_ip: str) -> bool:
        if self.settings.turnstile_test_mode:
            return hmac.compare_digest(token, self.settings.turnstile_test_token)
        if not token or not self.settings.turnstile_verify_url:
            return False
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.settings.upstream_timeout_seconds),
                verify=True,
                follow_redirects=False,
                trust_env=False,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    self.settings.turnstile_verify_url,
                    data={
                        "secret": self.settings.turnstile_secret_key,
                        "response": token,
                        "remoteip": remote_ip,
                    },
                )
            if response.status_code != 200 or len(response.content) > 64_000:
                return False
            payload = response.json()
        except (httpx.HTTPError, ValueError, TypeError):
            return False
        if not isinstance(payload, dict) or payload.get("success") is not True:
            return False
        expected_hostname = self.settings.turnstile_expected_hostname.strip().lower()
        hostname = payload.get("hostname")
        action = payload.get("action")
        if expected_hostname and (
            not isinstance(hostname, str) or hostname.strip().lower() != expected_hostname
        ):
            return False
        if self.settings.turnstile_expected_action and action != self.settings.turnstile_expected_action:
            return False
        return True
