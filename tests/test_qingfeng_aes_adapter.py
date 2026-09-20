from __future__ import annotations

import base64
import hashlib
import logging
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.adapters.qingfeng_aes import QingfengAesAdapter, QingfengSourceError
from app.services.aggregator import AccountAggregator

FIXTURES = Path(__file__).parent / "fixtures" / "qingfeng_aes"
URL = "https://feed.example.invalid/share/synthetic"
REFERER = "https://portal.example.invalid/"
SEED = "0123456789abcdef0123456789abcdef"


def encrypt(password: str, *, seed: str = SEED) -> str:
    key = hashlib.sha256(seed.encode("ascii")).digest()
    padder = padding.PKCS7(128).padder()
    padded = padder.update(password.encode("utf-8")) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(key[:16])).encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(encrypted).decode("ascii")


def html(*cards: str, script: str | None = None) -> bytes:
    seed_script = script or f'<script>const key = CryptoJS.SHA256("{SEED}");</script>'
    return (
        "<!doctype html><html><head><title>Shared accounts</title></head>"
        f"<body><main data-shared-accounts>{''.join(cards)}</main>{seed_script}</body></html>"
    ).encode()


def card(
    username: str,
    password: str,
    *,
    status: str = "状态: 正常",
    purchased: str = "美区已解锁小火箭",
    extra_class: str = "is-ready",
) -> str:
    return f"""
    <article data-account-card>
      <span class="account-status {extra_class}">{status}</span>
      <span class="purchase-status">{purchased}</span>
      <div class="account-row"><span class="label">Apple ID</span><span data-account-value>{username}</span></div>
      <div class="password-row"><span class="label">密码</span><button data-clipboard-text="{password}">复制</button></div>
    </article>
    """


def adapter(transport: httpx.AsyncBaseTransport | None = None) -> QingfengAesAdapter:
    return QingfengAesAdapter(
        alias="qingfeng",
        url=URL,
        referer=REFERER,
        timeout_seconds=2,
        max_response_bytes=50_000,
        transport=transport,
    )


def packed_script(seed: str = SEED) -> str:
    return (
        "<script>eval(function(p,a,c,k,e,d){e=function(c){return c.toString(a)};"
        "while(c--)if(k[c])p=p.replace(new RegExp('\\\\b'+e(c)+'\\\\b','g'),k[c]);return p}"
        f"(\"CryptoJS.SHA256('0')\",36,1,\"{seed}\".split(\"|\"),0,{{}}))</script>"
    )


@pytest.mark.asyncio
async def test_request_uses_exact_referer_and_fixed_generic_browser_headers() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == URL
        assert request.headers["referer"] == REFERER
        assert request.headers["accept"].startswith("text/html")
        assert request.headers["accept-language"] == "en-US,en;q=0.9"
        assert "Mozilla/5.0" in request.headers["user-agent"]
        rendered = "\n".join(f"{key}: {value}" for key, value in request.headers.items()).lower()
        assert "qingfeng" not in rendered
        assert "dabao" not in rendered
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=html(card("valid@example.invalid", encrypt("synthetic-password"))),
        )

    records = await adapter(httpx.MockTransport(handler)).fetch_accounts()
    assert [(item.username, item.password) for item in records] == [
        ("valid@example.invalid", "synthetic-password")
    ]
    assert records[0].features == ("shadowrocket_purchased",)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (httpx.Response(403, text="synthetic domain limit"), "referer_rejected"),
        (httpx.Response(302, headers={"location": "https://redirect.example.invalid/"}), "network_failed"),
        (httpx.Response(200, headers={"content-type": "application/json"}, content=b"{}"), "markup_drift"),
        (httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html><title>Checking your browser</title></html>"), "challenge_returned"),
    ],
)
async def test_fetch_failures_are_fixed_classifications(response: httpx.Response, reason: str) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return response

    with pytest.raises(QingfengSourceError) as caught:
        await adapter(httpx.MockTransport(handler)).fetch_accounts()
    assert caught.value.reason == reason


def test_direct_seed_status_purchase_filtering_and_same_card_pairing() -> None:
    body = html(
        card("first@example.invalid", encrypt("synthetic-first")),
        card("locked@example.invalid", encrypt("synthetic-locked"), status="状态: 异常", extra_class=""),
        card("not-purchased@example.invalid", encrypt("synthetic-unpurchased"), purchased="普通账号"),
        card("second@example.invalid", encrypt("synthetic-second")),
    )
    records = adapter().parse_response(body)
    assert [(item.username, item.password) for item in records] == [
        ("first@example.invalid", "synthetic-first"),
        ("second@example.invalid", "synthetic-second"),
    ]


def custom_packed_script(seed: str = SEED) -> str:
    payload = f"CryptoJS.SHA256('{seed}')".encode("utf-8")
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz|ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    radix = 36
    separator = alphabet[radix]
    encoded = separator.join(_base36(byte) for byte in payload)
    return (
        "<script>eval(function(h,u,n,t,e,r){return h}"
        f"(\"{encoded}\",0,\"{alphabet}\",0,{radix},0));</script>"
    )


def _base36(value: int) -> str:
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    if value == 0:
        return "0"
    result = ""
    while value:
        value, remainder = divmod(value, 36)
        result = alphabet[remainder] + result
    return result


def test_packed_seed_variants_are_safely_unpacked() -> None:
    for script in (packed_script(), custom_packed_script()):
        records = adapter().parse_response(
            html(card("packed@example.invalid", encrypt("synthetic-packed")), script=script)
        )
        assert records[0].password == "synthetic-packed"


def test_conflicting_status_negative_purchase_and_cross_card_pairing_fail_closed() -> None:
    ambiguous = f"""
    <article data-account-card>
      <span class="account-status is-ready">状态: 正常</span>
      <span class="account-status">状态: 异常</span>
      <span class="purchase-status">美区已解锁小火箭</span>
      <span data-account-value>conflict@example.invalid</span>
      <div class="password-row"><button data-clipboard-text="{encrypt('synthetic-conflict')}">复制</button></div>
    </article>
    """
    negative_purchase = card(
        "negative@example.invalid",
        encrypt("synthetic-negative"),
        purchased="Shadowrocket 未购买",
    )
    nested = f"""
    <div class="card">
      <article data-account-card>
        <span class="account-status is-ready">状态: 正常</span>
        <span class="purchase-status">美区已解锁小火箭</span>
        <span data-account-value>cross@example.invalid</span>
      </article>
      <article data-account-card>
        <span class="account-status is-ready">状态: 正常</span>
        <span class="purchase-status">美区已解锁小火箭</span>
        <div class="password-row"><button data-clipboard-text="{encrypt('synthetic-cross')}">复制</button></div>
      </article>
    </div>
    """
    with pytest.raises(QingfengSourceError, match="decrypt_failed"):
        adapter().parse_response(html(ambiguous, negative_purchase, nested))


def test_multiple_distinct_seed_candidates_fail_closed() -> None:
    other_seed = "fedcba9876543210fedcba9876543210"
    script = (
        f'<script>CryptoJS.SHA256("{SEED}"); CryptoJS.SHA256("{other_seed}");</script>'
    )
    with pytest.raises(QingfengSourceError) as caught:
        adapter().parse_response(
            html(card("ambiguous@example.invalid", encrypt("synthetic")), script=script)
        )
    assert caught.value.reason == "seed_ambiguous"


def test_direct_seed_decrypts_synthetic_ciphertext() -> None:
    records = adapter().parse_response(
        html(
            card("packed@example.invalid", encrypt("synthetic-packed")),
        )
    )
    assert records[0].password == "synthetic-packed"


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        (b"<html><main data-shared-accounts></main></html>", "referer_rejected"),
        (html(script=f'<script>CryptoJS.SHA256("{SEED}")</script>'), "markup_drift"),
        (html(card("bad@example.invalid", encrypt("synthetic")), script="<script>eval(alert(document.cookie))</script>"), "seed_missing"),
        (html(card("bad@example.invalid", encrypt("synthetic")), script="<script>eval(function(p,a,c,k,e,d){fetch('https://evil.example.invalid')}())</script>"), "unsafe_packer"),
    ],
)
def test_structural_seed_and_malicious_html_fail_closed(body: bytes, reason: str) -> None:
    with pytest.raises(QingfengSourceError) as caught:
        adapter().parse_response(body)
    assert caught.value.reason == reason


def test_bad_base64_padding_and_utf8_drop_only_the_bad_cards() -> None:
    key = hashlib.sha256(SEED.encode("ascii")).digest()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(key[:16])).encryptor()
    invalid_utf8_padded = b"\xff" + bytes([15]) * 15
    invalid_utf8 = base64.b64encode(encryptor.update(invalid_utf8_padded) + encryptor.finalize()).decode()
    body = html(
        card("good@example.invalid", encrypt("synthetic-good")),
        card("base64@example.invalid", "not strict base64!"),
        card("padding@example.invalid", base64.b64encode(bytes(16)).decode()),
        card("utf8@example.invalid", invalid_utf8),
    )
    records = adapter().parse_response(body)
    assert [(item.username, item.password) for item in records] == [
        ("good@example.invalid", "synthetic-good")
    ]


@pytest.mark.asyncio
async def test_all_bad_cards_do_not_replace_or_renew_existing_slice() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=html(card("bad@example.invalid", "%%%")),
        )

    class Store:
        async def replace_source_slice(self, *args, **kwargs):
            raise AssertionError("failed poll must not write")

    aggregator = AccountAggregator(store=Store(), adapters=[], id_secret="synthetic")  # type: ignore[arg-type]
    assert await aggregator.poll_once(adapter(httpx.MockTransport(handler))) is False


def test_adapter_requires_https_credential_free_urls_but_allows_explicit_cross_origin_referer() -> None:
    adapter()
    cases = [
        ("http://feed.example.invalid/share", REFERER),
        ("https://user:pass@feed.example.invalid/share", REFERER),
        (URL, "http://portal.example.invalid/"),
        (URL, "https://user:pass@portal.example.invalid/"),
    ]
    for url, referer in cases:
        with pytest.raises(ValueError, match="invalid qingfeng source"):
            QingfengAesAdapter(
                alias="qingfeng",
                url=url,
                referer=referer,
                timeout_seconds=2,
                max_response_bytes=50_000,
            )


def test_repr_and_logs_do_not_disclose_url_referer_or_credentials(caplog: pytest.LogCaptureFixture) -> None:
    configured = adapter()
    assert "example.invalid" not in repr(configured)
    secret = "synthetic-never-log-password"
    with caplog.at_level(logging.INFO):
        with pytest.raises(QingfengSourceError):
            configured.parse_response(html(card("secret@example.invalid", encrypt(secret)), script="<script></script>"))
    rendered = caplog.text
    assert "example.invalid" not in rendered
    assert secret not in rendered
