from __future__ import annotations

import logging
import secrets
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp, Receive, Scope, Send

from app.adapters.dom_source import DomSourceAdapter
from app.adapters.json_source import JsonSourceAdapter
from app.config import Settings
from app.models import (
    PublicAccount,
    RevealRequest,
    RevealResponse,
    FeedbackRequest,
    TicketResponse,
    VerifyRequest,
)
from app.security import client_ip, turnstile_origin
from app.services.aggregator import AccountAggregator
from app.services.store import AsyncRedis, RedisStore
from app.services.turnstile import TurnstileVerifier

logger = logging.getLogger("app.api")
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
GENERIC_MESSAGES = {
    "rate_limited": "请求过于频繁",
    "service_unavailable": "服务暂不可用",
    "pool_unavailable": "服务暂不可用",
    "not_ready": "服务暂不可用",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, settings: Settings) -> None:
        super().__init__(app)
        origin = turnstile_origin(settings)
        script_src = "'self'" + (f" {origin}" if origin else "")
        frame_src = origin or "'none'"
        self.csp = (
            "default-src 'self'; "
            f"script-src {script_src}; "
            "style-src 'self'; img-src 'self' data:; connect-src 'self'; "
            f"frame-src {frame_src}; object-src 'none'; base-uri 'none'; "
            "form-action 'self'; frame-ancestors 'none'"
        )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        response.headers["Content-Security-Policy"] = self.csp
        return response


def api_error(status_code: int, code: str) -> JSONResponse:
    public_code = {
        "request_denied": "access_denied",
        "verification_failed": "access_denied",
        "pool_unavailable": "temporarily_unavailable",
        "service_unavailable": "temporarily_unavailable",
        "not_ready": "temporarily_unavailable",
    }.get(code, code)
    message = GENERIC_MESSAGES.get(code, "请求无法完成")
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": public_code, "message": message}},
    )


class SafeExceptionMiddleware:
    """Catch uncaught application exceptions before they reach the server logger."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        except Exception:
            logger.error("request_failed result=internal_failure")
            response = api_error(503, "service_unavailable")
            response.headers.update(
                {
                    "Cache-Control": "no-store, max-age=0",
                    "Pragma": "no-cache",
                    "X-Content-Type-Options": "nosniff",
                    "Referrer-Policy": "no-referrer",
                    "X-Robots-Tag": "noindex, nofollow, noarchive",
                }
            )
            await response(scope, receive, send)


def _raise(status_code: int, code: str) -> None:
    raise HTTPException(status_code=status_code, detail=code)


def _require_browser_request(request: Request, settings: Settings) -> None:
    requested_with = request.headers.get("X-Requested-With")
    csrf_token = request.headers.get("X-CSRF-Token")
    if requested_with != "XMLHttpRequest" and not csrf_token:
        _raise(403, "request_denied")

    fetch_site = request.headers.get("Sec-Fetch-Site", "").lower()
    if fetch_site == "cross-site":
        _raise(403, "request_denied")

    origin = request.headers.get("Origin")
    if settings.public_origin and origin != settings.public_origin:
        _raise(403, "request_denied")


def _build_aggregator(settings: Settings, store: RedisStore) -> AccountAggregator:
    source_a = JsonSourceAdapter(
        alias="source_a",
        url=settings.source_a_url,
        timeout_seconds=settings.upstream_timeout_seconds,
        max_response_bytes=settings.upstream_max_response_bytes,
        unhealthy_markers=settings.unhealthy_markers,
    )
    source_b = DomSourceAdapter(
        alias="source_b",
        url=settings.source_b_url,
        referer=settings.source_b_referer,
        timeout_seconds=settings.upstream_timeout_seconds,
        max_response_bytes=settings.upstream_max_response_bytes,
        unhealthy_markers=settings.unhealthy_markers,
    )
    return AccountAggregator(
        store=store,
        adapters=[
            (source_a, settings.source_a_interval_seconds),
            (source_b, settings.source_b_interval_seconds),
        ],
        id_secret=settings.id_hmac_secret,
    )


def create_app(
    *,
    settings: Settings | None = None,
    redis_client: AsyncRedis | None = None,
    turnstile: TurnstileVerifier | None = None,
    aggregator: AccountAggregator | None = None,
    start_pollers: bool | None = None,
) -> FastAPI:
    runtime_settings = (settings or Settings.from_env()).validated()
    if start_pollers is not None:
        runtime_settings = runtime_settings.with_overrides(start_pollers=start_pollers)
    managed_redis = redis_client is None
    initial_store: RedisStore | None = (
        RedisStore(redis_client, runtime_settings) if redis_client is not None else None
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client: AsyncRedis = redis_client or Redis.from_url(
            runtime_settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            retry_on_timeout=False,
        )
        store = RedisStore(client, runtime_settings)
        runtime_aggregator = aggregator or _build_aggregator(runtime_settings, store)
        app.state.settings = runtime_settings
        app.state.store = store
        app.state.turnstile = turnstile or TurnstileVerifier(runtime_settings)
        app.state.aggregator = runtime_aggregator
        try:
            await store.ping()
            if runtime_settings.start_pollers:
                runtime_aggregator.start()
            yield
        finally:
            await runtime_aggregator.stop()
            if managed_redis:
                close = getattr(client, "aclose", None)
                if close is not None:
                    await close()

    app = FastAPI(
        title="Account Share v2",
        version="2.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    # Install state eagerly as well as in lifespan so in-process ASGI clients
    # that do not drive lifespan still exercise the real Redis-backed paths.
    if initial_store is not None:
        app.state.settings = runtime_settings
        app.state.store = initial_store
        app.state.turnstile = turnstile or TurnstileVerifier(runtime_settings)
        app.state.aggregator = aggregator or _build_aggregator(runtime_settings, initial_store)

    app.add_middleware(SecurityHeadersMiddleware, settings=runtime_settings)
    app.add_middleware(SafeExceptionMiddleware)
    app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")
    app.state.settings = runtime_settings
    if initial_store is not None:
        app.state.store = initial_store
        app.state.turnstile = turnstile or TurnstileVerifier(runtime_settings)
        app.state.aggregator = aggregator or _build_aggregator(runtime_settings, initial_store)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        code = exc.detail if isinstance(exc.detail, str) else "request_denied"
        return api_error(exc.status_code, code)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request,
        _exc: RequestValidationError,
    ) -> JSONResponse:
        return api_error(400, "invalid_request")

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_request: Request, _exc: Exception) -> JSONResponse:
        return api_error(503, "service_unavailable")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/robots.txt", include_in_schema=False)
    async def robots() -> Response:
        return Response("User-agent: *\nDisallow: /\n", media_type="text/plain")

    @app.get("/healthz", include_in_schema=False)
    @app.get("/health/live", include_in_schema=False)
    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    @app.get("/health/ready", include_in_schema=False)
    async def readiness(request: Request) -> dict[str, str]:
        try:
            if not await request.app.state.store.ping():
                _raise(503, "not_ready")
            if await request.app.state.store.get_fresh_pool(now=int(time.time())) is None:
                _raise(503, "not_ready")
        except HTTPException:
            raise
        except Exception:
            _raise(503, "not_ready")
        return {"status": "ready"}

    @app.get("/api/v2/config", include_in_schema=False)
    async def browser_config() -> dict[str, str]:
        return {
            "turnstile_site_key": runtime_settings.turnstile_site_key,
            "turnstile_script_url": runtime_settings.turnstile_script_url,
            "turnstile_action": runtime_settings.turnstile_expected_action,
        }

    @app.post("/api/v2/session/verify", status_code=204, response_class=Response)
    async def verify_session(payload: VerifyRequest, request: Request, response: Response) -> Response:
        _require_browser_request(request, runtime_settings)
        ip = client_ip(request, runtime_settings)
        try:
            allowed = await request.app.state.store.allow_rate(
                "verify-ip", ip, runtime_settings.rate_verify_ip_limit
            )
        except Exception:
            _raise(503, "service_unavailable")
        if not allowed:
            _raise(429, "rate_limited")
        if not await request.app.state.turnstile.verify(payload.token, ip):
            _raise(403, "verification_failed")
        raw_session = secrets.token_urlsafe(32)
        try:
            await request.app.state.store.create_session(raw_session)
        except Exception:
            _raise(503, "service_unavailable")
        response.set_cookie(
            key=runtime_settings.cookie_name,
            value=raw_session,
            max_age=runtime_settings.session_ttl_seconds,
            httponly=True,
            secure=runtime_settings.cookie_secure,
            samesite="strict",
            path="/",
        )
        response.status_code = 204
        return response

    @app.post("/api/v2/reveal-ticket", response_model=TicketResponse)
    async def reveal_ticket(request: Request, response: Response) -> TicketResponse:
        _require_browser_request(request, runtime_settings)
        store: RedisStore = request.app.state.store
        raw_session = request.cookies.get(runtime_settings.cookie_name)
        try:
            session_digest_value = await store.session_digest_if_valid(raw_session)
            if raw_session is None:
                raw_session = secrets.token_urlsafe(32)
                session_digest_value = await store.create_session(raw_session)
                response.set_cookie(
                    runtime_settings.cookie_name,
                    raw_session,
                    max_age=runtime_settings.session_ttl_seconds,
                    httponly=True,
                    secure=runtime_settings.cookie_secure,
                    samesite="strict",
                    path="/",
                )
            elif session_digest_value is None:
                _raise(403, "request_denied")
                raise AssertionError("unreachable")
            session_digest: str = session_digest_value
            ip = client_ip(request, runtime_settings)
            ip_allowed = await store.allow_rate(
                "ticket-ip", ip, runtime_settings.rate_ticket_ip_limit
            )
            session_allowed = await store.allow_rate(
                "ticket-session",
                session_digest,
                runtime_settings.rate_ticket_session_limit,
            )
            if not ip_allowed or not session_allowed:
                _raise(429, "rate_limited")
            ticket = await store.create_ticket(session_digest, now=int(time.time()))
        except HTTPException:
            raise
        except Exception:
            _raise(503, "service_unavailable")
        return TicketResponse(ticket=ticket, expires_in=runtime_settings.ticket_ttl_seconds)

    @app.post("/api/v2/accounts/reveal", response_model=RevealResponse)
    async def reveal_accounts(payload: RevealRequest, request: Request) -> RevealResponse:
        _require_browser_request(request, runtime_settings)
        store: RedisStore = request.app.state.store
        raw_session = request.cookies.get(runtime_settings.cookie_name)
        try:
            session_digest_value = await store.session_digest_if_valid(raw_session)
            if session_digest_value is None:
                _raise(403, "request_denied")
                raise AssertionError("unreachable")
            session_digest = session_digest_value
            if not await store.consume_ticket(
                payload.ticket,
                session_digest,
                now=int(time.time()),
            ):
                _raise(403, "request_denied")
            pool = await store.get_fresh_pool()
            ip = client_ip(request, runtime_settings)
            ip_allowed = await store.allow_rate(
                "reveal-ip", ip, runtime_settings.rate_reveal_ip_limit
            )
            session_allowed = await store.allow_rate(
                "reveal-session",
                session_digest,
                runtime_settings.rate_reveal_session_limit,
            )
            if not ip_allowed or not session_allowed:
                _raise(429, "rate_limited")
            if pool is None:
                return RevealResponse(
                    total=0,
                    updated_at=int(time.time()),
                    accounts=[],
                    exhausted=True,
                    purchase_link=runtime_settings.store_url or None,
                )
            selected = await store.select_account_for_session(
                session_digest,
                pool.accounts,
                intent=payload.intent,
                now=int(time.time()),
            )
            if selected is None:
                return RevealResponse(
                    total=0,
                    updated_at=pool.updated_at,
                    accounts=[],
                    exhausted=True,
                    purchase_link=runtime_settings.store_url or None,
                )
            await store.mark_account_shown(session_digest, selected.id)
        except HTTPException:
            raise
        except Exception:
            _raise(503, "service_unavailable")
            raise AssertionError("unreachable")
        return RevealResponse(
            total=1,
            updated_at=pool.updated_at,
            accounts=[PublicAccount(**selected.model_dump())],
            exhausted=False,
            purchase_link=runtime_settings.store_url or None,
        )

    @app.post("/api/v2/accounts/feedback", status_code=204)
    async def account_feedback(payload: FeedbackRequest, request: Request) -> Response:
        _require_browser_request(request, runtime_settings)
        store: RedisStore = request.app.state.store
        raw_session = request.cookies.get(runtime_settings.cookie_name)
        try:
            session_digest = await store.session_digest_if_valid(raw_session)
            if session_digest is None:
                _raise(403, "request_denied")
                raise AssertionError("unreachable")
            accepted = await store.record_account_feedback(
                session_digest,
                payload.account_id,
                payload.result,
                now=int(time.time()),
            )
            if not accepted:
                _raise(409, "request_denied")
        except HTTPException:
            raise
        except Exception:
            _raise(503, "service_unavailable")
        return Response(status_code=204)

    return app
