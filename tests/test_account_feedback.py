from __future__ import annotations

import pytest

from app.models import InternalAccount
from app.services.store import RedisStore


def account(account_id: str, username: str, synced: int = 100) -> InternalAccount:
    return InternalAccount(
        id=account_id,
        username=username,
        password="synthetic-password",
        region="US",
        status="active",
        last_synced_at=synced,
        features=[],
    )


@pytest.mark.asyncio
async def test_confirmed_shadowrocket_is_selected_before_unknown(redis_client, settings) -> None:
    store = RedisStore(redis_client, settings)
    known = account("acc_known", "known@example.invalid")
    unknown = account("acc_unknown", "unknown@example.invalid")
    feedback_session = await store.create_session("feedback-session", now=100)
    await store.mark_account_shown(feedback_session, known.id)
    assert await store.record_account_feedback(
        feedback_session, known.id, "shadowrocket_available", now=101
    )

    delivery_session = await store.create_session("delivery-session", now=102)
    selected = await store.select_account_for_session(
        delivery_session, [unknown, known], intent="target_app", now=103
    )

    assert selected == known


@pytest.mark.asyncio
async def test_no_shadowrocket_is_after_unknown_but_before_login_failed(redis_client, settings) -> None:
    store = RedisStore(redis_client, settings)
    session_a = await store.create_session("session-a", now=100)
    no_app = account("acc_no_app", "no-app@example.invalid")
    failed = account("acc_failed", "failed@example.invalid")
    unknown = account("acc_unknown", "unknown@example.invalid")

    for item, result in ((no_app, "shadowrocket_missing"), (failed, "login_failed")):
        await store.mark_account_shown(session_a, item.id)
        assert await store.record_account_feedback(session_a, item.id, result, now=101)

    session_b = await store.create_session("session-b", now=102)
    first = await store.select_account_for_session(session_b, [failed, no_app, unknown], now=103)
    assert first == unknown
    await store.mark_account_shown(session_b, first.id)
    second = await store.select_account_for_session(session_b, [failed, no_app, unknown], now=104)
    assert second == no_app
    await store.mark_account_shown(session_b, second.id)
    third = await store.select_account_for_session(session_b, [failed, no_app, unknown], now=105)
    assert third == failed


@pytest.mark.asyncio
async def test_other_app_intent_prefers_any_confirmed_login_over_unknown(redis_client, settings) -> None:
    store = RedisStore(redis_client, settings)
    feedback_session = await store.create_session("intent-feedback", now=100)
    confirmed_login = account("acc_login", "login@example.invalid")
    unknown = account("acc_unknown_intent", "unknown-intent@example.invalid")
    await store.mark_account_shown(feedback_session, confirmed_login.id)
    assert await store.record_account_feedback(
        feedback_session, confirmed_login.id, "shadowrocket_missing", now=101
    )

    delivery_session = await store.create_session("intent-delivery", now=102)
    selected = await store.select_account_for_session(
        delivery_session,
        [unknown, confirmed_login],
        intent="other_app",
        now=103,
    )
    assert selected == confirmed_login


@pytest.mark.asyncio
async def test_login_success_is_accepted_as_distinct_quality_signal(redis_client, settings) -> None:
    store = RedisStore(redis_client, settings)
    session = await store.create_session("login-success-session", now=100)
    item = account("acc_login_success", "login-success@example.invalid")
    await store.mark_account_shown(session, item.id)
    assert await store.record_account_feedback(session, item.id, "login_success", now=101)


@pytest.mark.asyncio
async def test_feedback_is_accepted_once_and_only_for_account_shown_to_session(redis_client, settings) -> None:
    store = RedisStore(redis_client, settings)
    session = await store.create_session("session-a", now=100)

    assert not await store.record_account_feedback(session, "acc_not_shown", "login_failed", now=101)
    await store.mark_account_shown(session, "acc_shown")
    assert await store.record_account_feedback(session, "acc_shown", "shadowrocket_available", now=102)
    assert not await store.record_account_feedback(session, "acc_shown", "login_failed", now=103)


@pytest.mark.asyncio
async def test_same_session_never_receives_same_account_twice(redis_client, settings) -> None:
    store = RedisStore(redis_client, settings)
    session = await store.create_session("session-a", now=100)
    first = account("acc_first", "first@example.invalid")
    second = account("acc_second", "second@example.invalid")

    selected = await store.select_account_for_session(session, [first, second], now=101)
    assert selected is not None
    await store.mark_account_shown(session, selected.id)

    selected_again = await store.select_account_for_session(session, [first, second], now=102)
    assert selected_again is not None
    assert selected_again.id != selected.id
    await store.mark_account_shown(session, selected_again.id)
    assert await store.select_account_for_session(session, [first, second], now=103) is None
