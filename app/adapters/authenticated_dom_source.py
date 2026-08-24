from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup, Tag

from app.adapters.base import (
    AdapterFetchError,
    BaseAdapter,
    contains_unhealthy_marker,
    upstream_ssl_context,
)
from app.adapters.json_source import EMAIL_RE
from app.models import CandidateAccount

logger = logging.getLogger("app.ingestion")
_TIME_RE = re.compile(r"(\d{4}-\d{1,2}-\d{1,2}[ T]\d{1,2}:\d{2}(?::\d{2})?)")
MAX_FIELD_LENGTH = 256
REASONS = {
    "ok",
    "empty_pool",
    "auth_expired",
    "challenge_returned",
    "markup_drift",
    "parse_failed",
    "upstream_stale",
    "network_failed",
}


class ReserveSourceError(AdapterFetchError):
    """A fixed, non-sensitive reserve ingestion classification."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason if reason in REASONS else "network_failed")
        self.reason = reason if reason in REASONS else "network_failed"


def _text(node: Tag) -> str:
    return " ".join(node.get_text(" ", strip=True).split())


def _attributes(node: Tag) -> list[str]:
    values: list[str] = []
    for child in [node, *node.find_all(True)]:
        if not isinstance(child, Tag):
            continue
        for value in child.attrs.values():
            if isinstance(value, str):
                values.append(value)
            elif isinstance(value, list):
                values.extend(str(item) for item in value)
    return values


def _labeled_value(item: Tag, label: str) -> str | None:
    matches: list[str] = []
    for value in item.select("[data-sky-shared-account-value]"):
        if not isinstance(value, Tag):
            continue
        parent = value.parent
        if not isinstance(parent, Tag):
            continue
        labels = [
            candidate
            for candidate in parent.find_all(["label", "dt", "span"], recursive=False)
            if isinstance(candidate, Tag)
        ]
        if len([candidate for candidate in labels if _text(candidate).rstrip("：:") == label]) != 1:
            continue
        rendered = _text(value)
        if rendered:
            matches.append(rendered)
    return matches[0] if len(matches) == 1 else None


class AuthenticatedDomSourceAdapter(BaseAdapter):
    def __init__(
        self,
        *,
        alias: str,
        url: str,
        cookie: str,
        timeout_seconds: float,
        max_response_bytes: int,
        unhealthy_markers: tuple[str, ...],
        sample_count: int,
        sample_jitter_ms: tuple[int, int],
        source_timezone: str,
        upstream_max_age_seconds: int,
        auth_failure_alert_threshold: int = 3,
        now: Callable[[], datetime] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        headers = {
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Encoding": "identity",
            "User-Agent": "AppleID-AutoShare-Reserve/1.0",
            "Cookie": cookie,
        }
        super().__init__(
            alias=alias,
            url=url,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
            unhealthy_markers=unhealthy_markers,
            headers=headers,
            transport=transport,
        )
        self._sample_count = sample_count
        self._jitter = sample_jitter_ms
        self._timezone = ZoneInfo(source_timezone)
        self._upstream_max_age = upstream_max_age_seconds
        self._alert_threshold = auth_failure_alert_threshold
        self._now = now or (lambda: datetime.now(tz=self._timezone))
        self._stats: dict[str, Any] = {
            "last_result": "never",
            "last_duration_ms": 0,
            "parsed_candidates": 0,
            "deduplicated_candidates": 0,
            "password_conflicts": 0,
            "consecutive_failures": 0,
            "last_success_at": None,
        }

    def _parse_time(self, text: str, label: str) -> int | None:
        position = text.find(label)
        if position < 0:
            return None
        match = _TIME_RE.search(text[position : position + len(label) + 40])
        if not match:
            return None
        parsed = datetime.fromisoformat(match.group(1)).replace(tzinfo=self._timezone)
        now = self._now().astimezone(self._timezone)
        if parsed > now:
            raise ReserveSourceError("upstream_stale")
        return int(parsed.timestamp())

    def _classify(self, soup: BeautifulSoup) -> Tag:
        title = soup.title.get_text(" ", strip=True).lower() if soup.title else ""
        page = soup.get_text(" ", strip=True).lower()
        if any(marker in title or marker in page for marker in ("checking your browser", "browser verification", "security challenge")):
            raise ReserveSourceError("challenge_returned")
        if soup.select_one('input[type="password"]') is not None and any(marker in page for marker in ("login", "sign in", "登录")):
            raise ReserveSourceError("auth_expired")
        root = soup.select_one("[data-sky-knowledge-shared-accounts]")
        if not isinstance(root, Tag):
            raise ReserveSourceError("markup_drift")
        return root

    async def _fetch_html_bytes(self) -> bytes:
        timeout = httpx.Timeout(self._timeout_seconds)
        async with httpx.AsyncClient(
            timeout=timeout,
            verify=upstream_ssl_context(),
            follow_redirects=False,
            trust_env=False,
            transport=self._transport,
        ) as client:
            async with client.stream("GET", self._url, headers=self._headers) as response:
                if response.status_code in {401, 403}:
                    raise ReserveSourceError("auth_expired")
                if response.status_code != 200:
                    raise ReserveSourceError("network_failed")
                media_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if media_type not in {"text/html", "application/xhtml+xml"}:
                    raise ReserveSourceError("markup_drift")
                declared = response.headers.get("content-length")
                if declared:
                    try:
                        if int(declared) > self._max_response_bytes:
                            raise ReserveSourceError("network_failed")
                    except ValueError as exc:
                        raise ReserveSourceError("network_failed") from exc
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > self._max_response_bytes:
                        raise ReserveSourceError("network_failed")
                    chunks.append(chunk)
                return b"".join(chunks)

    def parse_response(self, body: bytes) -> list[CandidateAccount]:
        try:
            html = body.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ReserveSourceError("markup_drift") from exc
        soup = BeautifulSoup(html, "html.parser")
        root = self._classify(soup)
        groups = [group for group in root.select("[data-sky-shared-account-group]") if isinstance(group, Tag)]
        if not groups:
            raise ReserveSourceError("markup_drift")
        records: list[CandidateAccount] = []
        available_claimed = False
        recognized_unavailable = False
        unknown_group_status = False
        now_ts = int(self._now().timestamp())
        stale_seen = False
        for group in groups:
            status_nodes = [
                node
                for node in group.select(":scope > header .group-status, :scope > .group-status")
                if isinstance(node, Tag)
            ]
            if not status_nodes:
                direct_statuses = [
                    node
                    for node in group.find_all(["span", "div"], recursive=False)
                    if isinstance(node, Tag) and _text(node) in {"可用", "不可用"}
                ]
                status_nodes = direct_statuses
            if len(status_nodes) != 1:
                unknown_group_status = True
                continue
            group_status = _text(status_nodes[0])
            if group_status != "可用":
                recognized_unavailable = True
                continue
            available_claimed = True
            group_text = _text(group)
            upstream = self._parse_time(group_text, "来源更新时间")
            relay = self._parse_time(group_text, "本站同步时间")
            if upstream is not None and now_ts - upstream > self._upstream_max_age:
                stale_seen = True
                continue
            for item in group.select(":scope > .sky-shared-account-item"):
                if not isinstance(item, Tag):
                    continue
                status_nodes = item.select(".sky-shared-account-status.is-ready")
                if len(status_nodes) != 1 or _text(status_nodes[0]) != "正常":
                    continue
                if contains_unhealthy_marker((_text(item), _attributes(item)), self._unhealthy_markers):
                    continue
                username = _labeled_value(item, "Apple ID")
                password = _labeled_value(item, "密码")
                if (
                    username is None
                    or password is None
                    or len(username) > MAX_FIELD_LENGTH
                    or len(password) > MAX_FIELD_LENGTH
                    or not EMAIL_RE.fullmatch(username)
                    or contains_unhealthy_marker((username, password), self._unhealthy_markers)
                ):
                    continue
                records.append(
                    CandidateAccount(
                        username=username,
                        password=password,
                        region="Unknown",
                        features=(),
                        upstream_updated_at=upstream,
                        relay_synced_at=relay,
                    )
                )
        if not records:
            if stale_seen:
                raise ReserveSourceError("upstream_stale")
            if available_claimed:
                raise ReserveSourceError("parse_failed")
            if unknown_group_status:
                raise ReserveSourceError("markup_drift")
            if recognized_unavailable:
                raise ReserveSourceError("empty_pool")
            raise ReserveSourceError("markup_drift")
        return self._deduplicate(records)

    def _deduplicate(self, records: list[CandidateAccount]) -> list[CandidateAccount]:
        unique: dict[str, CandidateAccount] = {}
        conflicts = 0
        for record in records:
            key = record.username.casefold()
            current = unique.get(key)
            if current is not None and current.password != record.password:
                conflicts += 1
            current_time = current.upstream_updated_at if current else None
            if current is None or (record.upstream_updated_at or 0) > (current_time or 0):
                unique[key] = record
        self._stats["password_conflicts"] = int(self._stats["password_conflicts"]) + conflicts
        return list(unique.values())

    async def fetch_accounts(self) -> list[CandidateAccount]:
        started = time.monotonic()
        successes: list[CandidateAccount] = []
        parsed_count = 0
        reason = "network_failed"
        try:
            for index in range(self._sample_count):
                if index:
                    delay_ms = random.randint(*self._jitter)
                    if delay_ms:
                        await asyncio.sleep(delay_ms / 1000)
                try:
                    body = await self._fetch_html_bytes()
                    sample = self.parse_response(body)
                    successes.extend(sample)
                    parsed_count += len(sample)
                except ReserveSourceError as exc:
                    reason = exc.reason
                    if reason in {"auth_expired", "challenge_returned"}:
                        raise
                    continue
                except (AdapterFetchError, httpx.HTTPError, UnicodeError, ValueError, TypeError):
                    reason = "network_failed"
                    continue
            if not successes:
                raise ReserveSourceError(reason)
            deduplicated = self._deduplicate(successes)
            reason = "ok"
            self._stats["consecutive_failures"] = 0
            self._stats["last_success_at"] = int(self._now().timestamp())
            return deduplicated
        except ReserveSourceError as exc:
            reason = exc.reason
            self._stats["consecutive_failures"] = int(self._stats["consecutive_failures"]) + 1
            if reason == "auth_expired" and int(self._stats["consecutive_failures"]) >= self._alert_threshold:
                logger.warning("reserve_auth_rotation_required alias=%s reason=auth_expired", self.alias)
            raise
        finally:
            duration = int((time.monotonic() - started) * 1000)
            self._stats.update(
                last_result=reason,
                last_duration_ms=duration,
                parsed_candidates=parsed_count,
                deduplicated_candidates=len(self._deduplicate(successes)) if successes else 0,
            )
            logger.info(
                "reserve_fetch alias=%s result=%s latency_ms=%d parsed=%d deduplicated=%d consecutive_failures=%d",
                self.alias,
                reason,
                duration,
                parsed_count,
                self._stats["deduplicated_candidates"],
                self._stats["consecutive_failures"],
            )

    def observability_snapshot(self) -> dict[str, Any]:
        return dict(self._stats)
