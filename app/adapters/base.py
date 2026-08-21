from __future__ import annotations

import logging
import ssl
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import certifi
import httpx

from app.models import CandidateAccount

logger = logging.getLogger("app.ingestion")
SUPPLEMENTAL_CA_PATH = Path(__file__).resolve().parents[2] / "certs" / "isrg-root-ye.pem"


def upstream_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=certifi.where())
    if SUPPLEMENTAL_CA_PATH.is_file():
        context.load_verify_locations(cafile=str(SUPPLEMENTAL_CA_PATH))
    return context


class AdapterFetchError(RuntimeError):
    """A deliberately generic upstream fetch or parse failure."""


class BaseAdapter(ABC):
    def __init__(
        self,
        *,
        alias: str,
        url: str,
        timeout_seconds: float,
        max_response_bytes: int,
        unhealthy_markers: tuple[str, ...],
        headers: dict[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.alias = alias
        self._url = url
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._unhealthy_markers = unhealthy_markers
        self._headers = headers or {}
        self._transport = transport

    async def _fetch_bytes(self) -> bytes:
        timeout = httpx.Timeout(self._timeout_seconds)
        async with httpx.AsyncClient(
            timeout=timeout,
            verify=upstream_ssl_context(),
            follow_redirects=False,
            trust_env=False,
            transport=self._transport,
        ) as client:
            async with client.stream("GET", self._url, headers=self._headers) as response:
                if response.status_code != 200:
                    raise AdapterFetchError("upstream_status")
                declared = response.headers.get("content-length")
                if declared:
                    try:
                        if int(declared) > self._max_response_bytes:
                            raise AdapterFetchError("response_too_large")
                    except ValueError as exc:
                        raise AdapterFetchError("invalid_content_length") from exc
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > self._max_response_bytes:
                        raise AdapterFetchError("response_too_large")
                    chunks.append(chunk)
                return b"".join(chunks)

    async def fetch_accounts(self) -> list[CandidateAccount]:
        started = time.monotonic()
        result_class = "failure"
        count = 0
        try:
            body = await self._fetch_bytes()
            records = self.parse_response(body)
            if not records:
                result_class = "empty"
                return []
            count = len(records)
            result_class = "success"
            return records
        except AdapterFetchError:
            raise
        except (httpx.HTTPError, UnicodeError, ValueError, TypeError) as exc:
            raise AdapterFetchError("upstream_failure") from exc
        finally:
            latency_ms = int((time.monotonic() - started) * 1000)
            logger.info(
                "upstream_fetch alias=%s result=%s latency_ms=%d count=%d",
                self.alias,
                result_class,
                latency_ms,
                count,
            )

    @abstractmethod
    def parse_response(self, body: bytes) -> list[CandidateAccount]:
        raise NotImplementedError


def contains_unhealthy_marker(values: Any, markers: tuple[str, ...]) -> bool:
    def flatten(value: Any) -> list[str]:
        if isinstance(value, dict):
            result: list[str] = []
            for child in value.values():
                result.extend(flatten(child))
            return result
        if isinstance(value, (list, tuple)):
            result = []
            for child in value:
                result.extend(flatten(child))
            return result
        if isinstance(value, str):
            return [value]
        return []

    texts = flatten(values)
    return any(marker in text for marker in markers for text in texts)
