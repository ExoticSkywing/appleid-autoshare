#!/usr/bin/env python3
"""Authorized, redacted reserve probe. Secrets are read only from the environment."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.adapters.authenticated_dom_source import (  # noqa: E402
    AuthenticatedDomSourceAdapter,
    ReserveSourceError,
)
from app.adapters.ikuuu_source import IkuuuSourceAdapter, IkuuuSourceError  # noqa: E402


def _required(name: str) -> str:
    value = os.getenv(name, "")
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


async def probe() -> dict[str, object]:
    if os.getenv("SOURCE_PROBE", "C").upper() == "D":
        adapter_d = IkuuuSourceAdapter(
            alias="reserve_d",
            url=_required("SOURCE_D_URL"),
            cookie=_required("SOURCE_D_COOKIE"),
            referer=_required("SOURCE_D_REFERER"),
            timeout_seconds=float(os.getenv("UPSTREAM_TIMEOUT_SECONDS", "8")),
            max_response_bytes=int(os.getenv("UPSTREAM_MAX_RESPONSE_BYTES", "1000000")),
            unhealthy_markers=(),
        )
        try:
            accounts_d = await adapter_d.fetch_accounts()
        except IkuuuSourceError as exc:
            return {"classification": exc.reason, "account_count": 0}
        return {"classification": "ok", "account_count": len(accounts_d)}
    adapter = AuthenticatedDomSourceAdapter(
        alias="reserve_c",
        url=_required("SOURCE_C_URL"),
        cookie=_required("SOURCE_C_COOKIE"),
        timeout_seconds=float(os.getenv("UPSTREAM_TIMEOUT_SECONDS", "8")),
        max_response_bytes=int(os.getenv("UPSTREAM_MAX_RESPONSE_BYTES", "1000000")),
        unhealthy_markers=("已锁定", "无法获取验证码", "需验证码", "密码错误", "异常", "失效"),
        sample_count=int(os.getenv("SOURCE_C_SAMPLE_COUNT", "3")),
        sample_jitter_ms=(
            int(os.getenv("SOURCE_C_SAMPLE_JITTER_MIN_MS", "250")),
            int(os.getenv("SOURCE_C_SAMPLE_JITTER_MAX_MS", "750")),
        ),
        source_timezone=os.getenv("SOURCE_C_TIMEZONE", "UTC"),
        upstream_max_age_seconds=int(os.getenv("SOURCE_C_UPSTREAM_MAX_AGE_SECONDS", "900")),
    )
    try:
        accounts = await adapter.fetch_accounts()
    except ReserveSourceError as exc:
        return {"classification": exc.reason, "account_count": 0, "max_source_age_seconds": None}
    now = int(datetime.now(tz=timezone.utc).timestamp())
    timestamps = [item.upstream_updated_at for item in accounts if item.upstream_updated_at is not None]
    return {
        "classification": "ok",
        "account_count": len(accounts),
        "max_source_age_seconds": max((now - value for value in timestamps), default=None),
    }


def main() -> int:
    try:
        print(json.dumps(asyncio.run(probe()), sort_keys=True))
    except (RuntimeError, ValueError):
        print(json.dumps({"classification": "configuration_error"}, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
