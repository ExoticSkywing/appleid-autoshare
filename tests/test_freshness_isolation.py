from __future__ import annotations

import pytest

from app.models import InternalAccount
from app.services.store import RedisStore


def account(username: str, password: str, synced: int) -> InternalAccount:
    return InternalAccount(
        id=f"acc_{username.split('@', maxsplit=1)[0]}",
        username=username,
        password=password,
        region="US",
        status="active",
        last_synced_at=synced,
        features=["shadowrocket_purchased"],
    )


@pytest.mark.asyncio
async def test_refreshing_one_source_never_renews_another_source(redis_client, settings) -> None:
    store = RedisStore(redis_client, settings)
    await store.replace_source_slice(
        "source_b",
        100,
        [account("stale@example.invalid", "synthetic-stale", 100)],
    )
    await store.replace_source_slice(
        "source_a",
        160,
        [account("fresh@example.invalid", "synthetic-fresh", 160)],
    )

    pool = await store.build_fresh_pool(("source_a", "source_b"), now=160)

    assert pool is not None
    assert [item.username for item in pool.accounts] == ["fresh@example.invalid"]


@pytest.mark.asyncio
async def test_slice_valid_until_is_immutable_across_config_changes(redis_client, settings) -> None:
    strict_store = RedisStore(redis_client, settings.with_overrides(source_freshness_seconds=30))
    await strict_store.replace_source_slice(
        "source_a",
        100,
        [account("person@example.invalid", "synthetic-secret", 100)],
    )

    relaxed_store = RedisStore(redis_client, settings.with_overrides(source_freshness_seconds=60))
    source = await relaxed_store.get_fresh_source_slice("source_a", now=131)

    assert source is None
