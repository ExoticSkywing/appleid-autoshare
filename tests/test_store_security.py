from __future__ import annotations

import pytest

from app.services.store import RedisStore


@pytest.mark.asyncio
async def test_ticket_is_bound_to_session_and_consumed_once(redis_client, settings) -> None:
    store = RedisStore(redis_client, settings)
    session = await store.create_session("203.0.113.10", now=100)
    ticket = await store.create_ticket(session, now=101)

    assert await store.consume_ticket(ticket, session, now=101) is True
    assert await store.consume_ticket(ticket, session, now=101) is False


@pytest.mark.asyncio
async def test_ticket_session_mismatch_consumes_ticket_fail_closed(redis_client, settings) -> None:
    store = RedisStore(redis_client, settings)
    session = await store.create_session("203.0.113.10", now=100)
    other = await store.create_session("203.0.113.11", now=100)
    ticket = await store.create_ticket(session, now=101)

    assert await store.consume_ticket(ticket, other, now=101) is False
    assert await store.consume_ticket(ticket, session, now=101) is False


@pytest.mark.asyncio
async def test_fixed_window_rate_limit_is_redis_backed(redis_client, settings) -> None:
    store = RedisStore(redis_client, settings)

    assert await store.allow_request("reveal_ip", "203.0.113.10", limit=2, window=60, now=119)
    assert await store.allow_request("reveal_ip", "203.0.113.10", limit=2, window=60, now=119)
    assert not await store.allow_request("reveal_ip", "203.0.113.10", limit=2, window=60, now=119)
    assert await store.allow_request("reveal_ip", "203.0.113.10", limit=2, window=60, now=120)
