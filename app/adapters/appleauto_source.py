from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.adapters.base import AdapterFetchError, BaseAdapter, contains_unhealthy_marker, upstream_ssl_context
from app.models import CandidateAccount

logger = logging.getLogger("app.ingestion")


class AppleAutoSourceAdapter(BaseAdapter):
    def __init__(
        self,
        *,
        alias: str = "appleauto",
        url: str,
        api_key: str,
        timeout_seconds: float = 10.0,
        max_response_bytes: int = 1_000_000,
        unhealthy_markers: tuple[str, ...] = (),
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            alias=alias,
            url=url.rstrip("/"),
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
            unhealthy_markers=unhealthy_markers,
            headers={
                "Accept": "application/json",
                "X-API-Key": api_key,
                "User-Agent": "autoshare-appleauto-v2",
            },
            transport=transport,
        )
        self.api_key = api_key

    async def fetch_accounts(self) -> list[CandidateAccount]:
        endpoint = f"{self._url}/client/getAllAccounts"
        timeout = httpx.Timeout(self._timeout_seconds)
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                verify=upstream_ssl_context(),
                transport=self._transport,
                headers=self._headers,
            ) as client:
                response = await client.get(endpoint)
                if response.status_code != 200:
                    raise AdapterFetchError("upstream_status")
                data = response.json()
                return self.parse_accounts(data, self._unhealthy_markers)
        except Exception as exc:
            logger.warning("appleauto_fetch_failed: %s", exc)
            raise AdapterFetchError(f"appleauto fetch failed: {exc}") from exc

    async def restart_account(self, account_upstream_id: int) -> bool:
        endpoint = f"{self._url}/client/restartAccount"
        timeout = httpx.Timeout(self._timeout_seconds)
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                verify=upstream_ssl_context(),
                transport=self._transport,
                headers=self._headers,
            ) as client:
                response = await client.post(endpoint, json={"id": account_upstream_id})
                data = response.json()
                return bool(data.get("ret") == 1 or data.get("status") is True or "success" in str(data).lower())
        except Exception as exc:
            logger.warning("appleauto_restart_failed id=%s: %s", account_upstream_id, exc)
            return False

    def parse_response(self, body: bytes) -> list[CandidateAccount]:
        data = json.loads(body.decode("utf-8"))
        return self.parse_accounts(data, self._unhealthy_markers)

    @staticmethod
    def parse_accounts(data: Any, unhealthy_markers: tuple[str, ...]) -> list[CandidateAccount]:
        if not isinstance(data, list):
            return []
        results: list[CandidateAccount] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            username = item.get("username")
            password = item.get("password")
            if not isinstance(username, str) or not isinstance(password, str):
                continue
            username = username.strip()
            password = password.strip()
            if not username or not password:
                continue
            if contains_unhealthy_marker(username, unhealthy_markers) or contains_unhealthy_marker(password, unhealthy_markers):
                continue
            upstream_id = item.get("id")
            # Feature tag: source_appleauto + shadowrocket_purchased + upstream id
            features: list[str] = ["source_appleauto", "shadowrocket_purchased"]
            if upstream_id is not None:
                features.append(f"appleauto_id_{upstream_id}")
            results.append(
                CandidateAccount(
                    username=username,
                    password=password,
                    region=str(item.get("region_display") or "US"),
                    features=tuple(features),
                    source_valid_until=None,
                )
            )
        return results
