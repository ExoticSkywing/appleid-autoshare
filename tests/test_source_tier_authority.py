from __future__ import annotations

import pytest
from app.models import InternalAccount
from app.services.store import RedisStore


def account(
    account_id: str,
    username: str,
    password: str = "pwd",
    synced: int = 100,
    features: list[str] | None = None,
) -> InternalAccount:
    return InternalAccount(
        id=account_id,
        username=username,
        password=password,
        region="US",
        status="active",
        last_synced_at=synced,
        features=list(features if features is not None else []),
    )


@pytest.mark.asyncio
async def test_ikuuu_tier0_is_always_first_even_after_failure_feedback(redis_client, settings) -> None:
    store = RedisStore(redis_client, settings)
    session_a = await store.create_session("session-a", now=100)

    # ikuuu 特权号（来源 Tier 0）
    ikuuu = account(
        "acc_ikuuu",
        "ikuuu@example.com",
        features=["shadowrocket_purchased", "source_ikuuu"],
    )
    # 模拟用户反馈 ikuuu 无法登录
    await store.mark_account_shown(session_a, ikuuu.id, password=ikuuu.password)
    assert await store.record_account_feedback(session_a, ikuuu.id, "login_failed", now=101)

    # 其他好评号（甚至被反馈成功的普通号或清风号）
    qingfeng = account(
        "acc_qingfeng",
        "qingfeng@example.com",
        features=["shadowrocket_purchased", "source_qingfeng"],
    )
    general = account(
        "acc_general",
        "general@example.com",
        features=[],
    )

    # 在一个全新的会话中（比如刷新网页 / 重新开始）
    session_b = await store.create_session("session-b", now=102)

    # 无论小火箭通道还是其他通道，ikuuu 都死死排在第一位！
    for intent in ("target_app", "other_app", "expert"):
        selected = await store.select_account_for_session(
            session_b, [general, qingfeng, ikuuu], intent=intent, now=103
        )
        assert selected == ikuuu
