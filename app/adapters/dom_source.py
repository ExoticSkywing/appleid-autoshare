from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup, Tag

from app.adapters.base import BaseAdapter, contains_unhealthy_marker
from app.adapters.json_source import EMAIL_RE
from app.models import CandidateAccount

STATUS_RE = re.compile(r"(?:^|\s)状态\s*[:：]\s*正常(?:\s|$)")
ID_RE = re.compile(r"^username_(\d+)$")


def _is_card(tag: Tag) -> bool:
    if tag.name in {"article", "li"}:
        return True
    classes_value = tag.get("class")
    if isinstance(classes_value, str):
        classes = [classes_value.lower()]
    elif isinstance(classes_value, list):
        classes = [str(value).lower() for value in classes_value]
    else:
        classes = []
    return any("card" in value or value.startswith("col-") for value in classes)


def _closest_card(button: Tag) -> Tag | None:
    card: Tag | None = None
    for parent in button.parents:
        if not isinstance(parent, Tag) or parent.name in {"body", "html", "main"}:
            continue
        if _is_card(parent):
            # Return the nearest card. Layout systems often nest one account card
            # inside generic column/card shells; walking farther and rejecting the
            # outer shell drops otherwise unambiguous accounts.
            card = parent
            break
    return card


def _has_nested_card(card: Tag) -> bool:
    return any(isinstance(child, Tag) and _is_card(child) for child in card.find_all(recursive=True))


def _attribute_values(card: Tag) -> list[str]:
    values: list[str] = []
    for node in card.find_all(True):
        if not isinstance(node, Tag):
            continue
        for value in node.attrs.values():
            if isinstance(value, str):
                values.append(value)
            elif isinstance(value, list):
                values.extend(str(item) for item in value)
    return values


def _region(card: Tag) -> str:
    explicit = card.select_one(".region")
    if explicit and explicit.get_text(strip=True):
        return explicit.get_text(strip=True)
    for badge in card.select("span.badge"):
        text = badge.get_text(strip=True)
        if text and text != "正常" and "状态" not in text:
            return text
    return "Unknown"


class DomSourceAdapter(BaseAdapter):
    def __init__(
        self,
        *,
        alias: str,
        url: str,
        referer: str = "",
        timeout_seconds: float,
        max_response_bytes: int,
        unhealthy_markers: tuple[str, ...],
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "identity",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "close",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Sec-Ch-Ua": '"Chromium";v="124", "Not-A.Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Linux"',
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        }
        if referer:
            headers["Referer"] = referer
        super().__init__(
            alias=alias,
            url=url,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
            unhealthy_markers=unhealthy_markers,
            headers=headers,
            transport=transport,
        )

    @staticmethod
    def parse_html(html: str, unhealthy_markers: tuple[str, ...]) -> list[CandidateAccount]:
        soup = BeautifulSoup(html, "html.parser")
        result: list[CandidateAccount] = []
        for user_button in soup.find_all(id=ID_RE):
            if not isinstance(user_button, Tag):
                continue
            match = ID_RE.fullmatch(str(user_button.get("id", "")))
            if not match:
                continue
            card = _closest_card(user_button)
            if card is None:
                continue
            suffix = match.group(1)
            username_nodes = card.find_all(id=f"username_{suffix}")
            password_nodes = card.find_all(id=f"password_{suffix}")
            if (
                len(username_nodes) != 1
                or len(password_nodes) != 1
                or username_nodes[0] is not user_button
                or not isinstance(password_nodes[0], Tag)
            ):
                continue
            password_button = password_nodes[0]
            card_text = card.get_text(" ", strip=True)
            status_nodes = [
                node
                for node in card.find_all(["div", "p", "span"])
                if isinstance(node, Tag) and STATUS_RE.search(node.get_text(" ", strip=True))
            ]
            if len(status_nodes) != 1:
                continue
            if contains_unhealthy_marker(card_text, unhealthy_markers):
                continue
            if contains_unhealthy_marker(_attribute_values(card), unhealthy_markers):
                continue
            username = user_button.get("data-clipboard-text")
            password = password_button.get("data-clipboard-text")
            if not isinstance(username, str) or not isinstance(password, str):
                continue
            username = username.strip()
            password = password.strip()
            if not EMAIL_RE.fullmatch(username) or not password:
                continue
            if contains_unhealthy_marker((username, password), unhealthy_markers):
                continue
            result.append(
                CandidateAccount(username=username, password=password, region=_region(card))
            )
        return result

    def parse_response(self, body: bytes) -> list[CandidateAccount]:
        return self.parse_html(body.decode("utf-8"), self._unhealthy_markers)
