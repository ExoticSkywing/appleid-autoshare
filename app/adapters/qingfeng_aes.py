from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import re
import time
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup, Tag
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.adapters.base import BaseAdapter, upstream_ssl_context
from app.models import CandidateAccount

logger = logging.getLogger("app.ingestion")

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_SEED_RE = re.compile(
    r"CryptoJS\s*\.\s*SHA256\s*\(\s*(['\"])([a-fA-F0-9]{32})\1\s*\)",
    re.IGNORECASE,
)
_PACKER_ARGS_RE = re.compile(
    r"return\s+p\s*\}\s*\(\s*\"(?P<payload>.*?)\"\s*,\s*"
    r"(?P<radix>\d+)\s*,\s*(?P<count>\d+)\s*,\s*\"(?P<symbols>.*?)\""
    r"\s*\.\s*split\(\s*\"\|\"\s*\)\s*,\s*\d+\s*,\s*\{\s*\}\s*\)\s*\)",
    re.DOTALL,
)
_CUSTOM_PACKER_RE = re.compile(
    r"\}\s*\(\s*(['\"])(?P<payload>(?:\\.|(?!\1).)*)\1\s*,\s*\d+\s*,\s*"
    r"(['\"])(?P<alphabet>(?:\\.|(?!\3).)*)\3\s*,\s*"
    r"(?P<offset>\d+)\s*,\s*(?P<radix>\d+)\s*,\s*\d+\s*\)\s*\)\s*;?",
    re.DOTALL,
)

_STATUS_SELECTORS = ".account-status, [data-account-status], .card-subtitle"
_PURCHASE_SELECTORS = ".purchase-status, [data-purchase-status], .card-subtitle"
_HEALTHY_VALUES = frozenset({"状态:正常", "状态：正常", "状态正常", "正常"})
_PURCHASE_VALUES = frozenset(
    {
        "账号信息:美区已解锁小火箭",
        "账号信息：美区已解锁小火箭",
        "美区已解锁小火箭",
        "已解锁小火箭",
        "美区已购小火箭",
        "已购小火箭",
        "美区已购买小火箭",
        "已购买小火箭",
    }
)
_CHALLENGE_MARKERS = (
    "checking your browser",
    "just a moment",
    "captcha",
    "cf-chl-",
    "challenge-platform",
)
_MAX_PACKED_SCRIPT_BYTES = 200_000
_MAX_PACKER_SYMBOLS = 4_096
_MAX_UNPACKED_BYTES = 500_000


class QingfengSourceError(RuntimeError):
    """Fixed, redacted failure classification for the encrypted HTML source."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class QingfengAesAdapter(BaseAdapter):
    def __init__(
        self,
        *,
        alias: str,
        url: str,
        referer: str,
        timeout_seconds: float,
        max_response_bytes: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not _valid_https_url(url) or not _valid_https_url(referer):
            raise ValueError("invalid qingfeng source endpoint configuration")
        super().__init__(
            alias=alias,
            url=url,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
            unhealthy_markers=(),
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Referer": referer,
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "cross-site",
                "Upgrade-Insecure-Requests": "1",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            },
            transport=transport,
        )

    def __repr__(self) -> str:
        return f"{type(self).__name__}(alias={self.alias!r})"

    async def _fetch_html_bytes(self) -> bytes:
        timeout = httpx.Timeout(self._timeout_seconds)
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                verify=upstream_ssl_context(),
                follow_redirects=False,
                trust_env=False,
                transport=self._transport,
            ) as client:
                async with client.stream("GET", self._url, headers=self._headers) as response:
                    if response.status_code == 403:
                        raise QingfengSourceError("referer_rejected")
                    if response.status_code != 200:
                        raise QingfengSourceError("network_failed")
                    media_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    if media_type not in {"text/html", "application/xhtml+xml"}:
                        raise QingfengSourceError("markup_drift")
                    declared = response.headers.get("content-length")
                    if declared:
                        try:
                            if int(declared) > self._max_response_bytes:
                                raise QingfengSourceError("network_failed")
                        except ValueError as exc:
                            raise QingfengSourceError("network_failed") from exc
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > self._max_response_bytes:
                            raise QingfengSourceError("network_failed")
                        chunks.append(chunk)
                    return b"".join(chunks)
        except QingfengSourceError:
            raise
        except httpx.HTTPError as exc:
            raise QingfengSourceError("network_failed") from exc

    async def fetch_accounts(self) -> list[CandidateAccount]:
        started = time.monotonic()
        reason = "network_failed"
        count = 0
        try:
            records = self.parse_response(await self._fetch_html_bytes())
            count = len(records)
            reason = "ok"
            return records
        except QingfengSourceError as exc:
            reason = exc.reason
            raise
        except (UnicodeError, ValueError, TypeError) as exc:
            reason = "markup_drift"
            raise QingfengSourceError(reason) from exc
        finally:
            duration = int((time.monotonic() - started) * 1000)
            logger.info(
                "source_fetch alias=%s result=%s latency_ms=%d count=%d",
                self.alias,
                reason,
                duration,
                count,
            )

    def parse_response(self, body: bytes) -> list[CandidateAccount]:
        try:
            html = body.decode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise QingfengSourceError("markup_drift") from exc
        folded = html.casefold()
        if any(marker in folded for marker in _CHALLENGE_MARKERS):
            raise QingfengSourceError("challenge_returned")

        soup = BeautifulSoup(html, "html.parser")
        cards = [
            card
            for card in soup.select("[data-account-card], .card")
            if isinstance(card, Tag) and not card.select_one("[data-account-card], .card")
        ]
        if not cards:
            source_signal = any(
                marker in script.get_text(" ", strip=False)
                for script in soup.select("script")
                for marker in ("eval", "CryptoJS.SHA256")
            )
            raise QingfengSourceError("markup_drift" if source_signal else "referer_rejected")
        seed = _extract_seed(soup)

        records: list[CandidateAccount] = []
        for card in cards:
            record = _parse_card(card, seed)
            if record is not None:
                records.append(record)
        if not records:
            raise QingfengSourceError("decrypt_failed")
        return _deduplicate(records)


def _valid_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.username is None
        and parsed.password is None
        and not any(char in value for char in "\r\n")
    )


def _extract_seed(soup: BeautifulSoup) -> str:
    packed_seen = False
    candidates: set[str] = set()
    for script in soup.select("script"):
        source = script.string or script.get_text(" ", strip=False)
        candidates.update(match.group(2).lower() for match in _SEED_RE.finditer(source))
        if "eval" not in source or "function" not in source:
            continue
        packed_seen = True
        if "function(h,u,n,t,e,r)" in source:
            unpacked = _unpack_custom_packer(source)
        else:
            unpacked = _unpack_dean_edwards(source)
        candidates.update(match.group(2).lower() for match in _SEED_RE.finditer(unpacked))
    if len(candidates) == 1:
        return next(iter(candidates))
    if len(candidates) > 1:
        raise QingfengSourceError("seed_ambiguous")
    if packed_seen:
        raise QingfengSourceError("unsafe_packer")
    raise QingfengSourceError("seed_missing")


def _decode_js_string(value: str) -> str:
    # Packer inputs are quoted JavaScript strings. Decode only the bounded escape
    # subset needed by the format; never execute JavaScript.
    out: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char != "\\":
            out.append(char)
            index += 1
            continue
        index += 1
        if index >= len(value):
            raise QingfengSourceError("unsafe_packer")
        escaped = value[index]
        mapping = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "v": "\v"}
        if escaped in mapping:
            out.append(mapping[escaped])
            index += 1
        elif escaped in {"\\", "'", '"', "/"}:
            out.append(escaped)
            index += 1
        elif escaped == "x" and index + 2 < len(value):
            try:
                out.append(chr(int(value[index + 1 : index + 3], 16)))
            except ValueError as exc:
                raise QingfengSourceError("unsafe_packer") from exc
            index += 3
        elif escaped == "u" and index + 4 < len(value):
            try:
                out.append(chr(int(value[index + 1 : index + 5], 16)))
            except ValueError as exc:
                raise QingfengSourceError("unsafe_packer") from exc
            index += 5
        else:
            raise QingfengSourceError("unsafe_packer")
    return "".join(out)


def _base_n(value: int, radix: int) -> str:
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if not 2 <= radix <= len(alphabet):
        raise QingfengSourceError("unsafe_packer")
    if value == 0:
        return "0"
    encoded: list[str] = []
    while value:
        value, remainder = divmod(value, radix)
        encoded.append(alphabet[remainder])
    return "".join(reversed(encoded))


def _unpack_custom_packer(source: str) -> str:
    """Decode the live source's bounded h/u/n/t/e/r character packer."""
    if len(source.encode("utf-8")) > _MAX_PACKED_SCRIPT_BYTES:
        raise QingfengSourceError("unsafe_packer")
    match = _CUSTOM_PACKER_RE.search(source)
    if not match:
        raise QingfengSourceError("unsafe_packer")
    payload = _decode_js_string(match.group("payload"))
    alphabet = _decode_js_string(match.group("alphabet"))
    offset = int(match.group("offset"))
    radix = int(match.group("radix"))
    if not 2 <= radix < len(alphabet) or len(alphabet) > 64:
        raise QingfengSourceError("unsafe_packer")
    separator = alphabet[radix]
    decoded: list[str] = []
    digit_values = {symbol: value for value, symbol in enumerate(alphabet[:radix])}
    for block in payload.split(separator):
        if not block or any(symbol not in digit_values for symbol in block):
            if not block:
                continue
            raise QingfengSourceError("unsafe_packer")
        codepoint = 0
        for symbol in block:
            codepoint = codepoint * radix + digit_values[symbol]
        codepoint -= offset
        if not 0 <= codepoint <= 255:
            raise QingfengSourceError("unsafe_packer")
        decoded.append(chr(codepoint))
        if len(decoded) > _MAX_UNPACKED_BYTES:
            raise QingfengSourceError("unsafe_packer")
    try:
        return "".join(decoded).encode("latin-1").decode("utf-8")
    except UnicodeError as exc:
        raise QingfengSourceError("unsafe_packer") from exc


def _unpack_dean_edwards(source: str) -> str:
    if len(source.encode("utf-8")) > _MAX_PACKED_SCRIPT_BYTES:
        raise QingfengSourceError("unsafe_packer")
    match = _PACKER_ARGS_RE.search(source)
    if not match:
        raise QingfengSourceError("unsafe_packer")
    radix = int(match.group("radix"))
    count = int(match.group("count"))
    if not 2 <= radix <= 62 or not 0 <= count <= _MAX_PACKER_SYMBOLS:
        raise QingfengSourceError("unsafe_packer")
    payload = _decode_js_string(match.group("payload"))
    symbols = _decode_js_string(match.group("symbols")).split("|")
    if count > len(symbols) or len(payload) > _MAX_UNPACKED_BYTES:
        raise QingfengSourceError("unsafe_packer")
    for index in range(count - 1, -1, -1):
        if not symbols[index]:
            continue
        token = _base_n(index, radix)
        replacement = symbols[index]
        payload = re.sub(rf"\b{re.escape(token)}\b", lambda _match: replacement, payload)
        if len(payload) > _MAX_UNPACKED_BYTES:
            raise QingfengSourceError("unsafe_packer")
    return payload


def _normalized_node_value(node: Tag, data_attribute: str) -> str:
    data_value = node.get(data_attribute)
    value = data_value if isinstance(data_value, str) else node.get_text(" ", strip=True)
    return re.sub(r"\s+", "", value).casefold()


def _unique_nodes(card: Tag, selector: str) -> list[Tag]:
    return [node for node in card.select(selector) if isinstance(node, Tag)]


def _parse_card(card: Tag, seed: str) -> CandidateAccount | None:
    all_status_nodes = _unique_nodes(card, _STATUS_SELECTORS)
    all_purchase_nodes = _unique_nodes(card, _PURCHASE_SELECTORS)
    status_nodes = [
        node
        for node in all_status_nodes
        if _normalized_node_value(node, "data-account-status") in _HEALTHY_VALUES
    ]
    purchase_nodes = [
        node
        for node in all_purchase_nodes
        if _normalized_node_value(node, "data-purchase-status") in _PURCHASE_VALUES
    ]
    explicit_status_nodes = [
        node
        for node in all_status_nodes
        if node.has_attr("data-account-status") or "account-status" in (node.get("class") or [])
    ]
    explicit_purchase_nodes = [
        node
        for node in all_purchase_nodes
        if node.has_attr("data-purchase-status") or "purchase-status" in (node.get("class") or [])
    ]
    if (
        len(status_nodes) != 1
        or len(purchase_nodes) != 1
        or len(explicit_status_nodes) > 1
        or len(explicit_purchase_nodes) > 1
    ):
        return None
    username_candidates = _unique_nodes(card, ".copy-btn[data-clipboard-text]") or _unique_nodes(
        card, "[data-account-value]"
    )
    password_candidates = _unique_nodes(card, ".copy-pass-btn[data-clipboard-text]") or _unique_nodes(
        card, "[data-password-ciphertext]"
    )
    if not password_candidates:
        username_ids = {id(node) for node in username_candidates}
        password_candidates = [
            node
            for node in _unique_nodes(card, ".password-row [data-clipboard-text]")
            if id(node) not in username_ids
        ]
    if len(username_candidates) != 1 or len(password_candidates) != 1:
        return None

    username_node = username_candidates[0]
    password_node = password_candidates[0]
    username_value = username_node.get("data-clipboard-text")
    username = (
        username_value.strip()
        if isinstance(username_value, str)
        else username_node.get_text(" ", strip=True)
    )
    ciphertext = password_node.get("data-clipboard-text") or password_node.get("data-password-ciphertext")
    if not _EMAIL_RE.fullmatch(username) or not isinstance(ciphertext, str):
        return None
    try:
        password = _decrypt_password(ciphertext, seed)
    except (ValueError, UnicodeError, binascii.Error, InvalidTag):
        return None
    if not password:
        return None
    return CandidateAccount(
        username=username,
        password=password,
        region="US",
        features=("shadowrocket_purchased",),
    )


def _decrypt_password(ciphertext_b64: str, seed: str) -> str:
    ciphertext = base64.b64decode(ciphertext_b64, validate=True)
    if not ciphertext or len(ciphertext) % 16:
        raise ValueError("invalid ciphertext")
    key = hashlib.sha256(seed.encode("ascii")).digest()
    decryptor = Cipher(algorithms.AES(key), modes.CBC(key[:16])).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    plaintext = unpadder.update(padded) + unpadder.finalize()
    return plaintext.decode("utf-8", errors="strict")


def _deduplicate(records: list[CandidateAccount]) -> list[CandidateAccount]:
    unique: dict[str, CandidateAccount] = {}
    for record in records:
        unique.setdefault(record.username.casefold(), record)
    return list(unique.values())
