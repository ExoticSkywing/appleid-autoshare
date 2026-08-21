from __future__ import annotations

import httpx
import pytest

from app.adapters.base import AdapterFetchError
from app.adapters.dom_source import DomSourceAdapter
from app.adapters.json_source import JsonSourceAdapter


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": 1},
        {"message": "异常"},
        {"last_check_success": True},
        {"last_check_success": 0},
        {"username": "not-an-email"},
        {"password": "   "},
    ],
)
def test_json_parser_keeps_only_strictly_healthy_records(overrides: dict[str, object]) -> None:
    valid = {
        "username": "person.one@example.invalid",
        "password": "synthetic-secret-one",
        "region_display": "US",
        "status": True,
        "message": "正常",
        "last_check_success": 1,
    }
    invalid = valid | overrides
    result = JsonSourceAdapter.parse_json({"accounts": [valid, invalid]}, ("已锁定", "需验证码"))

    assert len(result) == 1
    assert result[0].username == "person.one@example.invalid"
    assert result[0].password == "synthetic-secret-one"
    assert result[0].status == "active"


def test_json_parser_rejects_malformed_envelopes_and_unhealthy_markers() -> None:
    assert JsonSourceAdapter.parse_json([], ("已锁定",)) == []
    payload = {
        "accounts": [
            {
                "username": "person.two@example.invalid",
                "password": "synthetic-已锁定-secret",
                "region_display": "US",
                "status": True,
                "message": "正常",
                "last_check_success": 1,
            }
        ]
    }
    assert JsonSourceAdapter.parse_json(payload, ("已锁定",)) == []


def test_dom_parser_requires_same_suffix_same_card_exact_status_and_valid_email() -> None:
    html = """
    <main>
      <div class="account-card">
        <span class="region">US</span><div>状态: <span>正常</span></div>
        <button id="username_1" data-clipboard-text="person.one@example.invalid"></button>
        <button id="password_1" data-clipboard-text="synthetic-secret-one"></button>
      </div>
      <div class="account-card">
        <div>状态: <span>正常</span></div>
        <button id="username_2" data-clipboard-text="person.two@example.invalid"></button>
        <button id="password_3" data-clipboard-text="synthetic-secret-two"></button>
      </div>
      <div class="account-card">
        <div>状态: <span>异常正常</span></div>
        <button id="username_4" data-clipboard-text="person.four@example.invalid"></button>
        <button id="password_4" data-clipboard-text="synthetic-secret-four"></button>
      </div>
      <div class="account-card">
        <div>状态: <span>正常</span></div><p>账号已锁定</p>
        <button id="username_5" data-clipboard-text="person.five@example.invalid"></button>
        <button id="password_5" data-clipboard-text="synthetic-secret-five"></button>
      </div>
      <div class="account-card">
        <div>状态: <span>正常</span></div>
        <button id="username_6" data-clipboard-text="not-an-email"></button>
        <button id="password_6" data-clipboard-text="synthetic-secret-six"></button>
      </div>
    </main>
    """
    result = DomSourceAdapter.parse_html(html, ("已锁定", "需验证码"))

    assert [(record.username, record.password) for record in result] == [
        ("person.one@example.invalid", "synthetic-secret-one")
    ]
    assert result[0].region == "US"


def test_dom_parser_never_pairs_credentials_across_cards() -> None:
    html = """
    <div class="account-card"><div>状态: <span>正常</span></div>
      <button id="username_8" data-clipboard-text="person.eight@example.invalid"></button>
    </div>
    <div class="account-card"><div>状态: <span>正常</span></div>
      <button id="password_8" data-clipboard-text="synthetic-secret-eight"></button>
    </div>
    """
    assert DomSourceAdapter.parse_html(html, ()) == []


def test_dom_parser_rejects_ambiguous_or_hostile_card_structures() -> None:
    cases = [
        """
        <div class="account-card"><div>状态: <span>正常</span></div>
          <button id="username_1" data-clipboard-text="person.one@example.invalid"></button>
          <button id="password_1" data-clipboard-text="synthetic-one"></button>
          <button id="password_1" data-clipboard-text="synthetic-two"></button>
        </div>
        """,
        """
        <div class="account-card"><div>状态: <span>正常</span></div>
          <button id="username_2" data-clipboard-text="person.two@example.invalid"></button>
          <button id="username_2" data-clipboard-text="person.other@example.invalid"></button>
          <button id="password_2" data-clipboard-text="synthetic-two"></button>
        </div>
        """,
        """
        <div class="account-card"><div>状态: <span>正常</span></div>
          <span data-note="已锁定"></span>
          <button id="username_3" data-clipboard-text="person.three@example.invalid"></button>
          <button id="password_3" data-clipboard-text="synthetic-three"></button>
        </div>
        """,
        """
        <div class="account-card"><div>状态: <span>正常</span></div>
          <div class="account-card">
            <div>状态: <span>正常</span></div>
            <button id="username_4" data-clipboard-text="person.four@example.invalid"></button>
            <button id="password_4" data-clipboard-text="synthetic-four"></button>
            <button id="password_4" data-clipboard-text="synthetic-four-duplicate"></button>
          </div>
        </div>
        """,
    ]
    for html in cases:
        assert DomSourceAdapter.parse_html(html, ("已锁定",)) == []


def test_dom_parser_accepts_account_card_inside_generic_layout_shell() -> None:
    html = """
    <div class="col-md-6">
      <div class="card shadow-lg">
        <div class="card-body">
          <div>状态: <span>正常</span></div>
          <button id="username_188" data-clipboard-text="nested@example.invalid"></button>
          <button id="password_188" data-clipboard-text="synthetic-nested-secret"></button>
        </div>
      </div>
    </div>
    """
    result = DomSourceAdapter.parse_html(html, ())
    assert [(record.username, record.password) for record in result] == [
        ("nested@example.invalid", "synthetic-nested-secret")
    ]


@pytest.mark.asyncio
async def test_fetch_policy_does_not_follow_redirects_and_bounds_response_size() -> None:
    redirects: list[str] = []

    async def redirect_handler(request: httpx.Request) -> httpx.Response:
        redirects.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://redirect.invalid/secret"})

    adapter = JsonSourceAdapter(
        alias="source_a",
        url="https://configured.invalid/data",
        timeout_seconds=1,
        max_response_bytes=32,
        unhealthy_markers=(),
        transport=httpx.MockTransport(redirect_handler),
    )
    with pytest.raises(AdapterFetchError):
        await adapter.fetch_accounts()
    assert redirects == ["https://configured.invalid/data"]

    async def large_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 33)

    oversized = JsonSourceAdapter(
        alias="source_a",
        url="https://configured.invalid/data",
        timeout_seconds=1,
        max_response_bytes=32,
        unhealthy_markers=(),
        transport=httpx.MockTransport(large_handler),
    )
    with pytest.raises(AdapterFetchError, match="response_too_large"):
        await oversized.fetch_accounts()
