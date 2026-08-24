from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable

from app.adapters.base import AdapterFetchError, BaseAdapter
from app.adapters.ikuuu_source import IkuuuSourceError
from app.models import CandidateAccount, InternalAccount
from app.security import public_account_id
from app.services.store import RedisStore

logger = logging.getLogger("app.aggregation")


def deduplicate_accounts(accounts: Iterable[InternalAccount]) -> list[InternalAccount]:
    unique: dict[str, InternalAccount] = {}
    for account in accounts:
        key = account.username.strip().lower()
        current = unique.get(key)
        if current is None or _freshness_timestamp(account) > _freshness_timestamp(current):
            unique[key] = account
    return sorted(unique.values(), key=lambda item: (-_freshness_timestamp(item), item.id))


def _freshness_timestamp(account: InternalAccount) -> int:
    return account.upstream_updated_at or account.last_synced_at


class AccountAggregator:
    def __init__(
        self,
        *,
        store: RedisStore,
        adapters: list[tuple[BaseAdapter, int]],
        id_secret: str,
    ) -> None:
        self.store = store
        self.adapters = adapters
        self.id_secret = id_secret
        self._tasks: list[asyncio.Task[None]] = []
        self._stopping = asyncio.Event()
        self._rebuild_lock = asyncio.Lock()

    def _normalize(self, records: list[CandidateAccount], fetched_at: int) -> list[InternalAccount]:
        return [
            InternalAccount(
                id=public_account_id(record.username, self.id_secret),
                username=record.username,
                password=record.password,
                region=record.region,
                status="active",
                last_synced_at=fetched_at,
                features=list(record.features),
                upstream_updated_at=record.upstream_updated_at,
                relay_synced_at=record.relay_synced_at,
            )
            for record in records
        ]

    async def poll_once(self, adapter: BaseAdapter) -> bool:
        try:
            records = await adapter.fetch_accounts()
            if not records:
                return False
            fetched_at = int(time.time())
            accounts = self._normalize(records, fetched_at)
            authoritative_expiries = [
                record.source_valid_until
                for record in records
                if record.source_valid_until is not None
            ]
            stored = await self.store.replace_source_slice(
                adapter.alias,
                fetched_at,
                accounts,
                source_valid_until=min(authoritative_expiries) if authoritative_expiries else None,
            )
            return stored
        except IkuuuSourceError as exc:
            logger.warning("poll_failed alias=%s result=%s", adapter.alias, exc.reason)
            return False
        except (AdapterFetchError, ConnectionError, TimeoutError):
            logger.warning("poll_failed alias=%s result=failure", adapter.alias)
            return False
        except Exception:
            logger.error("poll_failed alias=%s result=internal_failure", adapter.alias)
            return False

    async def rebuild_pool(self, *, now: int | None = None) -> list[InternalAccount]:
        current = int(time.time()) if now is None else now
        async with self._rebuild_lock:
            all_accounts: list[InternalAccount] = []
            for adapter, _interval in self.adapters:
                source_slice = await self.store.get_fresh_source_slice(adapter.alias, now=current)
                if source_slice is not None:
                    all_accounts.extend(source_slice.accounts)
            return deduplicate_accounts(all_accounts)

    async def _poll_loop(self, adapter: BaseAdapter, interval: int) -> None:
        while not self._stopping.is_set():
            await self.poll_once(adapter)
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=interval)
            except TimeoutError:
                continue

    def start(self) -> None:
        if self._tasks:
            return
        self._stopping.clear()
        for adapter, interval in self.adapters:
            self._tasks.append(
                asyncio.create_task(
                    self._poll_loop(adapter, interval),
                    name=f"poll-{adapter.alias}",
                )
            )

    async def stop(self) -> None:
        self._stopping.set()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
