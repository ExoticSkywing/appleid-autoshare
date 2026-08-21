from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable

from app.adapters.base import AdapterFetchError, BaseAdapter
from app.models import CandidateAccount, InternalAccount
from app.security import public_account_id
from app.services.store import RedisStore

logger = logging.getLogger("app.aggregation")


def deduplicate_accounts(accounts: Iterable[InternalAccount]) -> list[InternalAccount]:
    unique: dict[str, InternalAccount] = {}
    for account in accounts:
        key = account.username.strip().lower()
        current = unique.get(key)
        if current is None or account.last_synced_at > current.last_synced_at:
            unique[key] = account
    return sorted(unique.values(), key=lambda item: (-item.last_synced_at, item.id))


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
            stored = await self.store.replace_source_slice(adapter.alias, fetched_at, accounts)
            return stored
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
