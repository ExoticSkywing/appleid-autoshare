from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from app.adapters.authenticated_dom_source import (
    AuthenticatedDomSourceAdapter,
    ReserveSourceError,
)

FIXTURES = Path(__file__).parent / "fixtures" / "reserve_source"
NOW = datetime(2026, 8, 24, 12, 10, tzinfo=timezone.utc)


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def adapter(
    transport: httpx.AsyncBaseTransport | None = None,
    *,
    samples: int = 3,
    jitter: tuple[int, int] = (0, 0),
) -> AuthenticatedDomSourceAdapter:
    return AuthenticatedDomSourceAdapter(
        alias="reserve_c",
        url="https://reserve.example.invalid/private",
        cookie="opaque-synthetic-session",
        timeout_seconds=2,
        max_response_bytes=50_000,
        unhealthy_markers=("异常", "失效", "已锁定"),
        sample_count=samples,
        sample_jitter_ms=jitter,
        source_timezone="UTC",
        upstream_max_age_seconds=900,
        now=lambda: NOW,
        transport=transport,
    )


def test_strict_parser_pairs_within_item_filters_health_and_deduplicates() -> None:
    records = adapter().parse_response(fixture("valid.html"))

    assert [(item.username, item.password) for item in records] == [
        ("person.one@example.invalid", "synthetic-new-password"),
        ("person.two@example.invalid", "synthetic-two-password"),
    ]
    assert records[0].upstream_updated_at == int(
        datetime(2026, 8, 24, 12, 5, tzinfo=timezone.utc).timestamp()
    )
    assert records[0].features == ()


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("challenge.html", "challenge_returned"),
        ("login.html", "auth_expired"),
        ("markup_drift.html", "markup_drift"),
        ("cross_card.html", "parse_failed"),
        ("malicious.html", "parse_failed"),
        ("unavailable.html", "empty_pool"),
    ],
)
def test_negative_fixtures_fail_closed(name: str, reason: str) -> None:
    with pytest.raises(ReserveSourceError, match=f"^{reason}$"):
        adapter().parse_response(fixture(name))


@pytest.mark.asyncio
async def test_bounded_sampling_merges_rotation_and_sends_opaque_cookie() -> None:
    calls = 0
    seen_headers: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        seen_headers.append(request.headers["cookie"])
        body = fixture("sample_one.html" if calls == 1 else "sample_two.html")
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, content=body)

    records = await adapter(httpx.MockTransport(handler), samples=3).fetch_accounts()

    assert calls == 3
    assert seen_headers == ["opaque-synthetic-session"] * 3
    assert {item.username for item in records} == {
        "rotation.one@example.invalid",
        "rotation.two@example.invalid",
    }


@pytest.mark.asyncio
async def test_auth_or_challenge_stops_sampling_immediately() -> None:
    calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        body = fixture("sample_one.html") if calls == 1 else fixture("challenge.html")
        return httpx.Response(200, headers={"content-type": "text/html"}, content=body)

    with pytest.raises(ReserveSourceError, match="^challenge_returned$"):
        await adapter(httpx.MockTransport(handler), samples=5).fetch_accounts()
    assert calls == 2


@pytest.mark.asyncio
async def test_partial_network_failure_can_still_replace_from_strict_successes() -> None:
    calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 2:
            return httpx.Response(503)
        return httpx.Response(200, headers={"content-type": "text/html"}, content=fixture("sample_one.html"))

    records = await adapter(httpx.MockTransport(handler), samples=3).fetch_accounts()
    assert len(records) == 1
    assert calls == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "reason"),
    [(401, "auth_expired"), (403, "auth_expired"), (302, "network_failed")],
)
async def test_http_status_classification(status: int, reason: str) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers={"location": "https://do-not-log.example.invalid/"})

    with pytest.raises(ReserveSourceError, match=f"^{reason}$"):
        await adapter(httpx.MockTransport(handler), samples=1).fetch_accounts()


@pytest.mark.asyncio
async def test_non_html_response_fails_closed() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/json"}, content=b"{}")

    with pytest.raises(ReserveSourceError, match="^markup_drift$"):
        await adapter(httpx.MockTransport(handler), samples=1).fetch_accounts()


@pytest.mark.asyncio
async def test_observability_is_redacted(caplog: pytest.LogCaptureFixture) -> None:
    secret = "opaque-never-log-this"

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, content=fixture("challenge.html"))

    configured = adapter(httpx.MockTransport(handler), samples=1)
    configured._headers["Cookie"] = secret
    with caplog.at_level(logging.INFO):
        with pytest.raises(ReserveSourceError):
            await configured.fetch_accounts()

    rendered = caplog.text
    assert secret not in rendered
    assert "reserve.example.invalid" not in rendered
    assert "challenge_returned" in rendered
    snapshot = configured.observability_snapshot()
    assert snapshot["last_result"] == "challenge_returned"
    assert snapshot["consecutive_failures"] == 1
    assert set(snapshot) >= {
        "last_result",
        "last_duration_ms",
        "parsed_candidates",
        "deduplicated_candidates",
        "consecutive_failures",
        "last_success_at",
    }
