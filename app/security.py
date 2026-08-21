from __future__ import annotations

import hashlib
import hmac
import ipaddress
from urllib.parse import urlparse

from fastapi import Request

from app.config import Settings


def keyed_digest(value: str, secret: str, namespace: str = "") -> str:
    message = f"{namespace}\0{value}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def public_account_id(username: str, secret: str) -> str:
    digest = keyed_digest(username.strip().lower(), secret, "account-id")
    return f"acc_{digest[:32]}"


def client_ip(request: Request, settings: Settings) -> str:
    candidate = request.client.host if request.client else "0.0.0.0"
    if settings.trust_proxy_headers:
        forwarded = request.headers.get(settings.proxy_ip_header, "")
        if forwarded:
            candidate = forwarded.split(",", maxsplit=1)[0].strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return "0.0.0.0"


def turnstile_origin(settings: Settings) -> str:
    if not settings.turnstile_script_url:
        return ""
    parsed = urlparse(settings.turnstile_script_url)
    return f"{parsed.scheme}://{parsed.netloc}"
