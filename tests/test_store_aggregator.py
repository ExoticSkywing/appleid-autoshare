from __future__ import annotations

import pytest

from app.models import InternalAccount
from app.security import public_account_id
from app.services.aggregator import deduplicate_accounts
from app.services.store import RedisStore


def account(username: str, password: str, synced: int) -> InternalAccount:
    return InternalAccount(
        id="acc_test",
        username=username,
        password=password,
        region="US",
        status="active",
        last_synced_at=synced,
        features=["shadowrocket_purchased"],
    )


def test_deduplicate_is_case_insensitive_and_prefers_freshest() -> None:
    older = account("Person.One@example.invalid", "synthetic-old", 100)
    newer = account("person.one@example.invalid", "synthetic-new", 101)
    other = account("person.two@example.invalid", "synthetic-other", 99)

    result = deduplicate_accounts([older, newer, other])

    assert [item.password for item in result] == ["synthetic-new", "synthetic-other"]


def test_deduplicate_prefers_newer_upstream_timestamp_over_later_relay_fetch() -> None:
    primary = account("same@example.invalid", "primary-new", 100)
    primary = primary.model_copy(update={"upstream_updated_at": 100})
    reserve = account("same@example.invalid", "reserve-old", 200)
    reserve = reserve.model_copy(update={"upstream_updated_at": 90})

    result = deduplicate_accounts([reserve, primary])

    assert [item.password for item in result] == ["primary-new"]


def test_public_id_is_stable_keyed_hmac_not_plain_username_hash() -> None:
    first = public_account_id("Person.One@example.invalid", "key-one")
    same = public_account_id("person.one@example.invalid", "key-one")
    other_key = public_account_id("person.one@example.invalid", "key-two")

    assert first == same
    assert first.startswith("acc_")
    assert first != other_key
    assert "person" not in first


@pytest.mark.asyncio
async def test_stale_source_is_excluded_and_pool_fails_closed(redis_client, settings) -> None:
    store = RedisStore(redis_client, settings)
    await store.replace_source_slice("source_a", 100, [account("fresh@example.invalid", "synthetic-fresh", 100)])
    await store.replace_source_slice("source_b", 39, [account("stale@example.invalid", "synthetic-stale", 39)])

    pool = await store.build_fresh_pool(("source_a", "source_b"), now=100)
    assert pool is not None
    assert [item.username for item in pool.accounts] == ["fresh@example.invalid"]

    assert await store.build_fresh_pool(("source_a", "source_b"), now=161) is None


@pytest.mark.asyncio
async def test_empty_refresh_does_not_replace_or_extend_source_slice(redis_client, settings) -> None:
    store = RedisStore(redis_client, settings)
    original = account("person@example.invalid", "synthetic-secret", 100)
    assert await store.replace_source_slice("source_a", 100, [original]) is True
    assert await store.replace_source_slice("source_a", 150, []) is False

    source = await store.get_fresh_source_slice("source_a", now=100)
    assert source is not None
    assert source.fetched_at == 100


@pytest.mark.asyncio
async def test_source_d_slice_is_capped_by_authoritative_expiry(redis_client, settings) -> None:
    configured = settings.with_overrides(source_d_freshness_seconds=300)
    store = RedisStore(redis_client, configured)
    item = account("reserve@example.invalid", "synthetic-secret", 100)
    assert await store.replace_source_slice(
        "reserve_d", 100, [item], source_valid_until=175
    ) is True
    source = await store.get_source_slice("reserve_d")
    assert source is not None
    assert source.valid_until == 175
    assert await store.get_fresh_source_slice("reserve_d", now=175) is None
