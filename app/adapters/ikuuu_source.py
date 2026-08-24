from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import httpx

from app.adapters.base import AdapterFetchError, BaseAdapter, upstream_ssl_context
from app.models import CandidateAccount

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_MAX_FUTURE_SECONDS = 366 * 24 * 60 * 60


class IkuuuSourceError(AdapterFetchError):
    """Fixed, redacted Source D failure classification."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class IkuuuSourceAdapter(BaseAdapter):
    def __init__(
        self,
        *,
        alias: str,
        url: str,
        cookie: str,
        referer: str,
        timeout_seconds: float,
        max_response_bytes: int,
        unhealthy_markers: tuple[str, ...],
        now: Callable[[], int] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        endpoint = urlparse(url)
        referrer = urlparse(referer)
        endpoint_origin = (endpoint.scheme, endpoint.hostname, endpoint.port)
        referrer_origin = (referrer.scheme, referrer.hostname, referrer.port)
        if (
            endpoint.scheme != "https"
            or not endpoint.hostname
            or endpoint.username is not None
            or endpoint.password is not None
            or referrer.scheme != "https"
            or not referrer.hostname
            or referrer.username is not None
            or referrer.password is not None
            or endpoint_origin != referrer_origin
        ):
            raise ValueError("invalid authenticated source endpoint configuration")
        super().__init__(
            alias=alias,
            url=url,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
            unhealthy_markers=unhealthy_markers,
            headers={
                "Accept": "application/json",
                "Cookie": cookie,
                "Referer": referer,
                "X-Requested-With": "XMLHttpRequest",
            },
            transport=transport,
        )
        self._now = now or (lambda: int(time.time()))

    def __repr__(self) -> str:
        return f"{type(self).__name__}(alias={self.alias!r})"

    async def _fetch_bytes(self) -> bytes:
        timeout = httpx.Timeout(self._timeout_seconds)
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                verify=upstream_ssl_context(),
                follow_redirects=False,
                trust_env=False,
                transport=self._transport,
            ) as client:
                async with client.stream("GET", self._url, headers=self._headers) as response:
                    if response.status_code in {401, 403}:
                        raise IkuuuSourceError("auth_expired")
                    if response.status_code != 200:
                        raise IkuuuSourceError("network_failed")
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    if content_type not in {"application/json", "text/json", "text/html"}:
                        raise IkuuuSourceError("schema_drift")
                    declared = response.headers.get("content-length")
                    if declared:
                        try:
                            if int(declared) > self._max_response_bytes:
                                raise IkuuuSourceError("network_failed")
                        except ValueError as exc:
                            raise IkuuuSourceError("network_failed") from exc
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > self._max_response_bytes:
                            raise IkuuuSourceError("network_failed")
                        chunks.append(chunk)
                    return b"".join(chunks)
        except IkuuuSourceError:
            raise
        except httpx.HTTPError as exc:
            raise IkuuuSourceError("network_failed") from exc

    def parse_response(self, body: bytes) -> list[CandidateAccount]:
        try:
            value: Any = json.loads(body)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise IkuuuSourceError("schema_drift") from exc
        if not isinstance(value, dict) or type(value.get("ret")) is not int:
            raise IkuuuSourceError("schema_drift")
        if value["ret"] != 1:
            raise IkuuuSourceError("auth_expired")
        data = value.get("data")
        if not isinstance(data, dict):
            raise IkuuuSourceError("schema_drift")
        username = data.get("ios_apple_id")
        password = data.get("ios_apple_id_password")
        expire_time = data.get("expire_time")
        if (
            not isinstance(username, str)
            or not _EMAIL_RE.fullmatch(username.strip())
            or not isinstance(password, str)
            or not password.strip()
            or type(expire_time) is not int
        ):
            raise IkuuuSourceError("schema_drift")
        current = self._now()
        if expire_time <= current or expire_time > current + _MAX_FUTURE_SECONDS:
            raise IkuuuSourceError("schema_drift")
        return [
            CandidateAccount(
                username=username.strip(),
                password=password,
                region="US",
                source_valid_until=expire_time,
            )
        ]
