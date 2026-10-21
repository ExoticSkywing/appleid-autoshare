from __future__ import annotations

import pytest
from app.models import InternalAccount
from app.services.store import RedisStore


def account(
    account_id: str,
    username: str,
    password: str = "pass123",
    synced: int = 100,
    features: list[str] | None = None,
) -> InternalAccount:
    return InternalAccount(
        id=account_id,
        username=username,
        password=password,
        region="美国",
        status="active",
        last_synced_at=synced,
        features=list(features if features is not None else ["shadowrocket_purchased"]),
    )


@pytest.mark.asyncio
async def test_password_change_resets_failure_quality(redis_client, settings) -> None:
    store = RedisStore(redis_client, settings)
    session = await store.create_session("session-test-pwd", now=100)
    
    # 1. 账号旧密码被标记为失败
    acc_old_pwd = account("acc_ikuuu", "ikuuu@example.com", password="old_password_123")
    await store.mark_account_shown(session, acc_old_pwd.id, password=acc_old_pwd.password)
    assert await store.record_account_feedback(session, acc_old_pwd.id, "login_failed", now=101)

    # 普通账号
    acc_general = account("acc_general", "general@example.com", password="pwd", features=[])

    # 2. 如果上游刷新了新密码，ikuuu 自动恢复为最高健康态
    acc_new_pwd = account("acc_ikuuu", "ikuuu@example.com", password="NEW_password_456")
    
    new_session = await store.create_session("session-test-new", now=102)
    selected = await store.select_account_for_session(new_session, [acc_general, acc_new_pwd], intent="target_app")
    assert selected == acc_new_pwd


@pytest.mark.asyncio
async def test_featured_account_even_with_failure_ranks_above_general_in_target_app(redis_client, settings) -> None:
    store = RedisStore(redis_client, settings)
    session = await store.create_session("session-test-fail-prio", now=100)

    # 特权号被标记失败
    acc_featured = account("acc_ikuuu", "ikuuu@example.com", password="same_password")
    await store.mark_account_shown(session, acc_featured.id, password=acc_featured.password)
    assert await store.record_account_feedback(session, acc_featured.id, "login_failed", now=101)

    # 普通号（无小火箭）
    acc_general = account("acc_general", "general@example.com", password="pwd", features=[])

    # 在 target_app 通道中，特权号依然优先于无小火箭的普通号
    new_session = await store.create_session("session-test-target", now=102)
    selected = await store.select_account_for_session(new_session, [acc_general, acc_featured], intent="target_app")
    assert selected == acc_featured
