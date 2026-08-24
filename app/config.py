from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ConfigurationError(ValueError):
    """Raised when security-sensitive runtime configuration is invalid."""


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be a boolean")


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc


def _float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number") from exc


def _markers(value: str | None) -> tuple[str, ...]:
    default = "已锁定,无法获取验证码,需验证码,密码错误,异常,失效"
    return tuple(item.strip() for item in (value or default).split(",") if item.strip())


def _https_url(name: str, value: str, required: bool) -> None:
    if not value:
        if required:
            raise ConfigurationError(f"{name} is required")
        return
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ConfigurationError(f"{name} must be an HTTPS URL without credentials")


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str = "development"
    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_prefix: str = "autoshare:v2"
    id_hmac_secret: str = ""
    state_hmac_secret: str = ""

    source_a_url: str = ""
    source_b_url: str = ""
    source_b_referer: str = ""
    source_a_interval_seconds: int = 45
    source_b_interval_seconds: int = 90
    source_c_enabled: bool = False
    source_c_url: str = field(default="", repr=False)
    source_c_cookie: str = field(default="", repr=False)
    source_c_interval_seconds: int = 300
    source_c_sample_count: int = 3
    source_c_sample_jitter_min_ms: int = 250
    source_c_sample_jitter_max_ms: int = 750
    source_c_freshness_seconds: int = 600
    source_c_upstream_max_age_seconds: int = 900
    source_c_slice_ttl_seconds: int = 1200
    source_c_timezone: str = "UTC"
    source_c_auth_failure_alert_threshold: int = 3
    source_d_enabled: bool = False
    source_d_url: str = field(default="", repr=False)
    source_d_cookie: str = field(default="", repr=False)
    source_d_referer: str = field(default="", repr=False)
    source_d_interval_seconds: int = 300
    source_d_freshness_seconds: int = 300
    source_d_slice_ttl_seconds: int = 600
    delivery_source_mode: str = "all"
    upstream_timeout_seconds: float = 8.0
    upstream_max_response_bytes: int = 1_000_000
    unhealthy_markers: tuple[str, ...] = (
        "已锁定",
        "无法获取验证码",
        "需验证码",
        "密码错误",
        "异常",
        "失效",
    )

    source_slice_ttl_seconds: int = 180
    source_freshness_seconds: int = 60
    pool_ttl_seconds: int = 60
    pool_freshness_seconds: int = 60

    turnstile_site_key: str = ""
    turnstile_secret_key: str = ""
    turnstile_verify_url: str = ""
    turnstile_script_url: str = ""
    turnstile_expected_hostname: str = ""
    turnstile_expected_action: str = "reveal"
    turnstile_test_mode: bool = False
    turnstile_test_token: str = ""

    session_ttl_seconds: int = 600
    ticket_ttl_seconds: int = 30
    cookie_name: str = "__Host-aid_session"
    cookie_secure: bool = True
    public_origin: str = ""
    trust_proxy_headers: bool = False
    proxy_ip_header: str = "CF-Connecting-IP"

    rate_window_seconds: int = 60
    rate_verify_ip_limit: int = 10
    rate_ticket_ip_limit: int = 10
    rate_ticket_session_limit: int = 10
    rate_reveal_ip_limit: int = 10
    rate_reveal_session_limit: int = 10
    reveal_max_accounts: int = 10
    store_url: str = ""
    start_pollers: bool = True

    @property
    def source_c_sample_jitter_ms(self) -> tuple[int, int]:
        return (self.source_c_sample_jitter_min_ms, self.source_c_sample_jitter_max_ms)

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            environment=os.getenv("APP_ENV", "development").strip().lower(),
            redis_url=os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"),
            redis_prefix=os.getenv("REDIS_PREFIX", "autoshare:v2"),
            id_hmac_secret=os.getenv("ID_HMAC_SECRET", ""),
            state_hmac_secret=os.getenv("STATE_HMAC_SECRET", ""),
            source_a_url=os.getenv("SOURCE_A_URL", ""),
            source_b_url=os.getenv("SOURCE_B_URL", ""),
            source_b_referer=os.getenv("SOURCE_B_REFERER", ""),
            source_a_interval_seconds=_int("SOURCE_A_POLL_SECONDS", 45),
            source_b_interval_seconds=_int("SOURCE_B_POLL_SECONDS", 90),
            source_c_enabled=_bool("SOURCE_C_ENABLED", False),
            source_c_url=os.getenv("SOURCE_C_URL", ""),
            source_c_cookie=os.getenv("SOURCE_C_COOKIE", ""),
            source_c_interval_seconds=_int("SOURCE_C_POLL_SECONDS", 300),
            source_c_sample_count=_int("SOURCE_C_SAMPLE_COUNT", 3),
            source_c_sample_jitter_min_ms=_int("SOURCE_C_SAMPLE_JITTER_MIN_MS", 250),
            source_c_sample_jitter_max_ms=_int("SOURCE_C_SAMPLE_JITTER_MAX_MS", 750),
            source_c_freshness_seconds=_int("SOURCE_C_FRESHNESS_SECONDS", 600),
            source_c_upstream_max_age_seconds=_int("SOURCE_C_UPSTREAM_MAX_AGE_SECONDS", 900),
            source_c_slice_ttl_seconds=_int("SOURCE_C_SLICE_TTL_SECONDS", 1200),
            source_c_timezone=os.getenv("SOURCE_C_TIMEZONE", "UTC"),
            source_c_auth_failure_alert_threshold=_int("SOURCE_C_AUTH_FAILURE_ALERT_THRESHOLD", 3),
            source_d_enabled=_bool("SOURCE_D_ENABLED", False),
            source_d_url=os.getenv("SOURCE_D_URL", ""),
            source_d_cookie=os.getenv("SOURCE_D_COOKIE", ""),
            source_d_referer=os.getenv("SOURCE_D_REFERER", ""),
            source_d_interval_seconds=_int("SOURCE_D_POLL_SECONDS", 300),
            source_d_freshness_seconds=_int("SOURCE_D_FRESHNESS_SECONDS", 300),
            source_d_slice_ttl_seconds=_int("SOURCE_D_SLICE_TTL_SECONDS", 600),
            delivery_source_mode=os.getenv("DELIVERY_SOURCE_MODE", "all").strip().lower(),
            upstream_timeout_seconds=_float("UPSTREAM_TIMEOUT_SECONDS", 8.0),
            upstream_max_response_bytes=_int("UPSTREAM_MAX_RESPONSE_BYTES", 1_000_000),
            unhealthy_markers=_markers(os.getenv("UNHEALTHY_MARKERS")),
            source_slice_ttl_seconds=_int("SOURCE_SLICE_TTL_SECONDS", 180),
            source_freshness_seconds=_int("SOURCE_FRESHNESS_SECONDS", 60),
            pool_ttl_seconds=_int("POOL_TTL_SECONDS", 60),
            pool_freshness_seconds=_int("POOL_FRESHNESS_SECONDS", 60),
            turnstile_site_key=os.getenv("TURNSTILE_SITE_KEY", ""),
            turnstile_secret_key=os.getenv("TURNSTILE_SECRET_KEY", ""),
            turnstile_verify_url=os.getenv("TURNSTILE_VERIFY_URL", ""),
            turnstile_script_url=os.getenv("TURNSTILE_SCRIPT_URL", ""),
            turnstile_expected_hostname=os.getenv("TURNSTILE_EXPECTED_HOSTNAME", ""),
            turnstile_expected_action=os.getenv("TURNSTILE_EXPECTED_ACTION", "reveal"),
            turnstile_test_mode=_bool("TURNSTILE_TEST_MODE", False),
            turnstile_test_token=os.getenv("TURNSTILE_TEST_TOKEN", ""),
            session_ttl_seconds=_int("SESSION_TTL_SECONDS", 600),
            ticket_ttl_seconds=_int("TICKET_TTL_SECONDS", 30),
            cookie_name=os.getenv("COOKIE_NAME", "__Host-aid_session"),
            cookie_secure=_bool("COOKIE_SECURE", True),
            public_origin=os.getenv("PUBLIC_ORIGIN", "").rstrip("/"),
            trust_proxy_headers=_bool("TRUST_PROXY_HEADERS", False),
            proxy_ip_header=os.getenv("PROXY_IP_HEADER", "CF-Connecting-IP"),
            rate_window_seconds=_int("RATE_WINDOW_SECONDS", 60),
            rate_verify_ip_limit=_int("RATE_VERIFY_IP_LIMIT", 10),
            rate_ticket_ip_limit=_int("RATE_TICKET_IP_LIMIT", 10),
            rate_ticket_session_limit=_int("RATE_TICKET_SESSION_LIMIT", 10),
            rate_reveal_ip_limit=_int("RATE_REVEAL_IP_LIMIT", 10),
            rate_reveal_session_limit=_int("RATE_REVEAL_SESSION_LIMIT", 10),
            reveal_max_accounts=_int("REVEAL_MAX_ACCOUNTS", 10),
            store_url=os.getenv("STORE_URL", "").strip(),
            start_pollers=_bool("START_POLLERS", True),
        ).validated()

    def with_overrides(self, **overrides: Any) -> Settings:
        return replace(self, **overrides).validated()

    def validated(self) -> Settings:
        production = self.environment == "production"
        if self.environment not in {"production", "development", "test"}:
            raise ConfigurationError("APP_ENV must be production, development, or test")
        if not 1 <= self.source_a_interval_seconds <= 3600:
            raise ConfigurationError("SOURCE_A_POLL_SECONDS must be between 1 and 3600")
        if not 1 <= self.source_b_interval_seconds <= 3600:
            raise ConfigurationError("SOURCE_B_POLL_SECONDS must be between 1 and 3600")
        if self.source_a_interval_seconds <= self.upstream_timeout_seconds:
            raise ConfigurationError("SOURCE_A_POLL_SECONDS must exceed UPSTREAM_TIMEOUT_SECONDS")
        if self.source_b_interval_seconds <= self.upstream_timeout_seconds:
            raise ConfigurationError("SOURCE_B_POLL_SECONDS must exceed UPSTREAM_TIMEOUT_SECONDS")
        if self.source_c_enabled:
            if not 1 <= self.source_c_sample_count <= 5:
                raise ConfigurationError("SOURCE_C_SAMPLE_COUNT must be between 1 and 5")
            if not 0 <= self.source_c_sample_jitter_min_ms <= self.source_c_sample_jitter_max_ms <= 10_000:
                raise ConfigurationError("source C sample jitter range is invalid")
            if self.source_c_interval_seconds <= self.upstream_timeout_seconds * self.source_c_sample_count:
                raise ConfigurationError("SOURCE_C_POLL_SECONDS must exceed the bounded network budget")
            if self.source_c_freshness_seconds <= 0 or self.source_c_upstream_max_age_seconds <= 0:
                raise ConfigurationError("source C freshness limits must be positive")
            if self.source_c_slice_ttl_seconds <= self.source_c_freshness_seconds:
                raise ConfigurationError("source C diagnostic TTL must exceed freshness")
            if self.source_c_auth_failure_alert_threshold <= 0:
                raise ConfigurationError("source C auth alert threshold must be positive")
            try:
                ZoneInfo(self.source_c_timezone)
            except ZoneInfoNotFoundError as exc:
                raise ConfigurationError("SOURCE_C_TIMEZONE is invalid") from exc
        if self.source_d_enabled:
            if self.source_d_interval_seconds <= self.upstream_timeout_seconds:
                raise ConfigurationError("SOURCE_D_POLL_SECONDS must exceed UPSTREAM_TIMEOUT_SECONDS")
            if self.source_d_freshness_seconds <= 0:
                raise ConfigurationError("SOURCE_D_FRESHNESS_SECONDS must be positive")
            if self.source_d_slice_ttl_seconds <= self.source_d_freshness_seconds:
                raise ConfigurationError("SOURCE_D_SLICE_TTL_SECONDS must exceed freshness")
        if not 1 <= self.source_freshness_seconds <= 60:
            raise ConfigurationError("source freshness must be between 1 and 60 seconds")
        if not 1 <= self.pool_ttl_seconds <= 60 or not 1 <= self.pool_freshness_seconds <= 60:
            raise ConfigurationError("pool TTL and freshness must be between 1 and 60 seconds")
        if self.source_slice_ttl_seconds <= self.source_freshness_seconds:
            raise ConfigurationError("source slice diagnostic TTL must exceed freshness")
        if self.upstream_timeout_seconds <= 0 or self.upstream_max_response_bytes < 1024:
            raise ConfigurationError("upstream network limits are invalid")
        if self.session_ttl_seconds <= 0 or self.ticket_ttl_seconds <= 0:
            raise ConfigurationError("session and ticket TTLs must be positive")
        if self.rate_window_seconds <= 0 or not 1 <= self.reveal_max_accounts <= 20:
            raise ConfigurationError("rate and reveal limits are invalid")
        if self.store_url:
            _https_url("STORE_URL", self.store_url, production)
        for value in (
            self.rate_verify_ip_limit,
            self.rate_ticket_ip_limit,
            self.rate_ticket_session_limit,
            self.rate_reveal_ip_limit,
            self.rate_reveal_session_limit,
        ):
            if value <= 0:
                raise ConfigurationError("rate limits must be positive")
        if not self.redis_url.startswith(("redis://", "rediss://")):
            raise ConfigurationError("REDIS_URL must use redis:// or rediss://")
        if not self.redis_prefix or any(ch.isspace() for ch in self.redis_prefix):
            raise ConfigurationError("REDIS_PREFIX is invalid")
        if not self.proxy_ip_header or any(ch in self.proxy_ip_header for ch in "\r\n:"):
            raise ConfigurationError("PROXY_IP_HEADER is invalid")
        if production:
            _https_url("PUBLIC_ORIGIN", self.public_origin, True)
            parsed_origin = urlparse(self.public_origin)
            if parsed_origin.path not in {"", "/"} or parsed_origin.query or parsed_origin.fragment:
                raise ConfigurationError("PUBLIC_ORIGIN must be an HTTPS origin without path/query/fragment")
            if not self.cookie_name.startswith("__Host-"):
                raise ConfigurationError("production COOKIE_NAME must use the __Host- prefix")

        if self.delivery_source_mode not in {
            "all",
            "primary_only",
            "source_a_only",
            "source_b_only",
            "reserve_only",
            "source_d_only",
            "ikuuu_only",
        }:
            raise ConfigurationError("DELIVERY_SOURCE_MODE is invalid")
        if self.delivery_source_mode == "reserve_only" and not self.source_c_enabled:
            raise ConfigurationError("reserve_only requires SOURCE_C_ENABLED=true")
        if self.delivery_source_mode in {"source_d_only", "ikuuu_only"} and not self.source_d_enabled:
            raise ConfigurationError("source_d_only requires SOURCE_D_ENABLED=true")
        require_upstreams = self.start_pollers
        _https_url("SOURCE_A_URL", self.source_a_url, require_upstreams)
        _https_url("SOURCE_B_URL", self.source_b_url, require_upstreams)
        _https_url("SOURCE_B_REFERER", self.source_b_referer, False)
        _https_url("SOURCE_C_URL", self.source_c_url, self.source_c_enabled)
        if self.source_c_enabled and not self.source_c_cookie:
            raise ConfigurationError("SOURCE_C_COOKIE is required")
        _https_url("SOURCE_D_URL", self.source_d_url, self.source_d_enabled)
        _https_url("SOURCE_D_REFERER", self.source_d_referer, self.source_d_enabled)
        if self.source_d_enabled:
            referer = urlparse(self.source_d_referer)
            endpoint = urlparse(self.source_d_url)
            if (referer.scheme, referer.hostname, referer.port) != (
                endpoint.scheme,
                endpoint.hostname,
                endpoint.port,
            ):
                raise ConfigurationError("SOURCE_D_REFERER must use the same origin as SOURCE_D_URL")
        if self.source_d_enabled and not self.source_d_cookie:
            raise ConfigurationError("SOURCE_D_COOKIE is required")

        if self.turnstile_test_mode:
            if production:
                raise ConfigurationError("Turnstile test mode is forbidden in production")
            if len(self.turnstile_test_token) < 12:
                raise ConfigurationError("explicit TURNSTILE_TEST_TOKEN is required in test mode")
        else:
            for turnstile_name, turnstile_value in (
                ("TURNSTILE_SITE_KEY", self.turnstile_site_key),
                ("TURNSTILE_SECRET_KEY", self.turnstile_secret_key),
                ("TURNSTILE_EXPECTED_HOSTNAME", self.turnstile_expected_hostname),
                ("TURNSTILE_EXPECTED_ACTION", self.turnstile_expected_action),
            ):
                if production and not turnstile_value:
                    raise ConfigurationError(f"{turnstile_name} is required")
            _https_url("TURNSTILE_VERIFY_URL", self.turnstile_verify_url, production)
            _https_url("TURNSTILE_SCRIPT_URL", self.turnstile_script_url, production)

        if production:
            if len(self.id_hmac_secret) < 32 or len(self.state_hmac_secret) < 32:
                raise ConfigurationError("production HMAC secrets must contain at least 32 characters")
            if not self.cookie_secure:
                raise ConfigurationError("secure cookies are required in production")
        return self
