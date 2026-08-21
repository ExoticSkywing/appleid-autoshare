from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.adapters.base import BaseAdapter, contains_unhealthy_marker
from app.models import CandidateAccount

EMAIL_RE = re.compile(r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+$", re.IGNORECASE)


class JsonSourceAdapter(BaseAdapter):
    def __init__(
        self,
        *,
        alias: str,
        url: str,
        timeout_seconds: float,
        max_response_bytes: int,
        unhealthy_markers: tuple[str, ...],
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            alias=alias,
            url=url,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
            unhealthy_markers=unhealthy_markers,
            headers={"Accept": "application/json", "User-Agent": "autoshare-v2"},
            transport=transport,
        )

    @staticmethod
    def parse_json(data: Any, unhealthy_markers: tuple[str, ...]) -> list[CandidateAccount]:
        if not isinstance(data, dict) or set(data).isdisjoint({"accounts"}):
            return []
        raw_accounts = data.get("accounts")
        if not isinstance(raw_accounts, list):
            return []

        result: list[CandidateAccount] = []
        for raw in raw_accounts:
            if not isinstance(raw, dict):
                continue
            if raw.get("status") is not True or raw.get("message") != "正常":
                continue
            last_success = raw.get("last_check_success")
            if type(last_success) is not int or last_success != 1:
                continue
            username = raw.get("username")
            password = raw.get("password")
            region = raw.get("region_display", "Unknown")
            if not isinstance(username, str) or not isinstance(password, str):
                continue
            username = username.strip()
            password = password.strip()
            if not EMAIL_RE.fullmatch(username) or not password:
                continue
            if contains_unhealthy_marker(raw, unhealthy_markers):
                continue
            if not isinstance(region, str) or not region.strip():
                region = "Unknown"
            result.append(
                CandidateAccount(username=username, password=password, region=region.strip())
            )
        return result

    def parse_response(self, body: bytes) -> list[CandidateAccount]:
        data = json.loads(body.decode("utf-8"))
        return self.parse_json(data, self._unhealthy_markers)
