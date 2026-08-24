from __future__ import annotations

import json
import secrets
import time
from typing import Any, Protocol

from app.config import Settings
from app.models import AggregatePool, InternalAccount, SourceSlice
from app.security import keyed_digest


class AsyncRedis(Protocol):
    async def get(self, name: str) -> Any: ...
    async def set(self, name: str, value: Any, **kwargs: Any) -> Any: ...
    async def sadd(self, name: str, *values: Any) -> Any: ...
    async def sismember(self, name: str, value: Any) -> Any: ...
    async def expire(self, name: str, seconds: int) -> Any: ...
    async def exists(self, name: str) -> Any: ...
    async def ping(self) -> Any: ...
    async def execute_command(self, *args: Any) -> Any: ...
    def pipeline(self, transaction: bool = True) -> Any: ...


class RedisStore:
    def __init__(self, redis: AsyncRedis, settings: Settings) -> None:
        self.redis = redis
        self.settings = settings

    def _key(self, *parts: str) -> str:
        return ":".join((self.settings.redis_prefix, *parts))

    def _state_digest(self, value: str, namespace: str) -> str:
        return keyed_digest(value, self.settings.state_hmac_secret, namespace)

    async def ping(self) -> bool:
        return bool(await self.redis.ping())

    async def replace_source_slice(
        self,
        alias: str,
        fetched_at: int,
        accounts: list[InternalAccount],
        *,
        source_valid_until: int | None = None,
    ) -> bool:
        if not accounts:
            return False
        source_limits = {
            "reserve_c": (
                self.settings.source_c_freshness_seconds,
                self.settings.source_c_slice_ttl_seconds,
            ),
            "reserve_d": (
                self.settings.source_d_freshness_seconds,
                self.settings.source_d_slice_ttl_seconds,
            ),
        }
        freshness, diagnostic_ttl = source_limits.get(
            alias,
            (self.settings.source_freshness_seconds, self.settings.source_slice_ttl_seconds),
        )
        valid_until = fetched_at + freshness
        if source_valid_until is not None:
            valid_until = min(valid_until, source_valid_until)
        if valid_until <= fetched_at:
            return False
        payload = SourceSlice(
            source_alias=alias,
            fetched_at=fetched_at,
            valid_until=valid_until,
            accounts=accounts,
        ).model_dump_json()
        await self.redis.set(
            self._key("source", alias),
            payload,
            ex=diagnostic_ttl,
        )
        return True

    async def get_source_slice(self, alias: str) -> SourceSlice | None:
        raw = await self.redis.get(self._key("source", alias))
        if raw is None:
            return None
        try:
            return SourceSlice.model_validate_json(raw)
        except (ValueError, TypeError):
            return None

    async def get_fresh_source_slice(
        self,
        alias: str,
        *,
        now: int | None = None,
    ) -> SourceSlice | None:
        current = int(time.time()) if now is None else now
        parsed = await self.get_source_slice(alias)
        if parsed is None or parsed.fetched_at > current or parsed.valid_until <= current:
            return None
        if alias == "reserve_c":
            accounts = [
                account
                for account in parsed.accounts
                if account.upstream_updated_at is None
                or 0 <= current - account.upstream_updated_at
                <= self.settings.source_c_upstream_max_age_seconds
            ]
            if not accounts:
                return None
            parsed.accounts = accounts
        return parsed

    async def build_fresh_pool(
        self,
        aliases: tuple[str, ...],
        *,
        now: int | None = None,
    ) -> AggregatePool | None:
        """Build a freshness-filtered view without extending stored TTLs."""
        current = int(time.time()) if now is None else now
        all_accounts: list[InternalAccount] = []
        for alias in aliases:
            source_slice = await self.get_fresh_source_slice(alias, now=current)
            if source_slice is not None:
                all_accounts.extend(source_slice.accounts)
        if not all_accounts:
            return None

        unique: dict[str, InternalAccount] = {}
        for account in all_accounts:
            key = account.username.strip().lower()
            previous = unique.get(key)
            account_freshness = account.upstream_updated_at or account.last_synced_at
            previous_freshness = (
                previous.upstream_updated_at or previous.last_synced_at
                if previous is not None
                else -1
            )
            if previous is None or account_freshness > previous_freshness:
                unique[key] = account
        accounts = sorted(
            unique.values(),
            key=lambda item: (-(item.upstream_updated_at or item.last_synced_at), item.id),
        )
        return AggregatePool(
            updated_at=max(item.last_synced_at for item in accounts),
            accounts=accounts,
        )

    async def get_fresh_pool(self, *, now: int | None = None) -> AggregatePool | None:
        aliases_by_mode = {
            "all": ("source_a", "source_b")
            + (("reserve_c",) if self.settings.source_c_enabled else ())
            + (("reserve_d",) if self.settings.source_d_enabled else ()),
            "primary_only": ("source_a", "source_b"),
            "source_a_only": ("source_a",),
            "source_b_only": ("source_b",),
            "reserve_only": ("reserve_c",),
            "source_d_only": ("reserve_d",),
            "ikuuu_only": ("reserve_d",),
        }
        aliases = aliases_by_mode[self.settings.delivery_source_mode]
        return await self.build_fresh_pool(aliases, now=now)

    async def create_session(self, raw_session: str, *, now: int | None = None) -> str:
        digest = self._state_digest(raw_session, "session")
        payload = json.dumps({"created_at": int(time.time()) if now is None else now})
        await self.redis.set(
            self._key("session", digest),
            payload,
            ex=self.settings.session_ttl_seconds,
        )
        return digest

    async def session_digest_if_valid(self, raw_session: str | None) -> str | None:
        if not raw_session:
            return None
        digest = self._state_digest(raw_session, "session")
        if not await self.redis.exists(self._key("session", digest)):
            return None
        return digest

    async def create_ticket(self, session_digest: str, *, now: int | None = None) -> str:
        current = int(time.time()) if now is None else now
        raw_ticket = secrets.token_urlsafe(32)
        ticket_digest = self._state_digest(raw_ticket, "ticket")
        payload = json.dumps(
            {
                "session_digest": session_digest,
                "issued_at": current,
                "valid_until": current + self.settings.ticket_ttl_seconds,
            }
        )
        await self.redis.set(
            self._key("ticket", ticket_digest),
            payload,
            ex=self.settings.ticket_ttl_seconds,
        )
        return raw_ticket

    async def consume_ticket(
        self,
        raw_ticket: str,
        session_digest: str,
        *,
        now: int | None = None,
    ) -> bool:
        current = int(time.time()) if now is None else now
        ticket_digest = self._state_digest(raw_ticket, "ticket")
        raw = await self.redis.execute_command("GETDEL", self._key("ticket", ticket_digest))
        if isinstance(raw, bytes):
            raw = raw.decode()
        if not isinstance(raw, str):
            return False
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            return False
        if not isinstance(payload, dict) or payload.get("session_digest") != session_digest:
            return False
        issued_at = payload.get("issued_at")
        valid_until = payload.get("valid_until")
        return (
            type(issued_at) is int
            and type(valid_until) is int
            and issued_at <= current <= valid_until
        )

    async def mark_account_shown(self, session_digest: str, account_id: str) -> None:
        key = self._key("session-shown", session_digest)
        await self.redis.sadd(key, account_id)
        await self.redis.expire(key, self.settings.session_ttl_seconds)

    async def select_account_for_session(
        self,
        session_digest: str,
        accounts: list[InternalAccount],
        *,
        intent: str = "target_app",
        now: int | None = None,
    ) -> InternalAccount | None:
        del now
        ranked: list[tuple[int, int, int, str, InternalAccount]] = []
        for account in accounts:
            if await self.redis.sismember(self._key("session-shown", session_digest), account.id):
                continue
            raw_quality = await self.redis.get(self._key("account-quality", account.id))
            quality = raw_quality.decode() if isinstance(raw_quality, bytes) else raw_quality
            rank = {
                "shadowrocket_available": 0,
                "login_success": 1,
                None: 2,
                "shadowrocket_missing": 3,
                "login_failed": 4,
            }.get(quality, 1)
            if intent == "target_app":
                intent_rank = 0 if quality == "shadowrocket_available" else 1
            else:
                intent_rank = 0 if quality in {"shadowrocket_available", "shadowrocket_missing", "login_success"} else 1
            ranked.append((intent_rank, rank, -account.last_synced_at, account.id, account))
        if not ranked:
            return None
        ranked.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
        return ranked[0][4]

    async def record_account_feedback(
        self,
        session_digest: str,
        account_id: str,
        result: str,
        *,
        now: int | None = None,
    ) -> bool:
        del now
        if result not in {"shadowrocket_available", "shadowrocket_missing", "login_success", "login_failed"}:
            return False
        shown_key = self._key("session-shown", session_digest)
        if not await self.redis.sismember(shown_key, account_id):
            return False
        once_key = self._key("session-feedback", session_digest, account_id)
        accepted = await self.redis.set(once_key, result, nx=True, ex=self.settings.session_ttl_seconds)
        if not accepted:
            return False
        await self.redis.set(self._key("account-quality", account_id), result)
        return True

    async def allow_request(
        self,
        bucket: str,
        identity: str,
        *,
        limit: int,
        window: int,
        now: int | None = None,
    ) -> bool:
        current = int(time.time()) if now is None else now
        window_number = current // window
        identity_digest = self._state_digest(identity, f"rate:{bucket}")[:32]
        key = self._key("rate", bucket, identity_digest, str(window_number))
        pipeline = self.redis.pipeline(transaction=True)
        pipeline.incr(key)
        pipeline.expire(key, window * 2)
        count, _ = await pipeline.execute()
        return int(count) <= limit

    async def allow_rate(
        self,
        bucket: str,
        identity: str,
        limit: int,
        *,
        now: int | None = None,
    ) -> bool:
        return await self.allow_request(
            bucket,
            identity,
            limit=limit,
            window=self.settings.rate_window_seconds,
            now=now,
        )
