from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CandidateAccount(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    username: str
    password: str
    region: str = "Unknown"
    status: Literal["active"] = "active"
    features: tuple[str, ...] = ("shadowrocket_purchased",)
    upstream_updated_at: int | None = None
    relay_synced_at: int | None = None
    # Internal authoritative upstream expiry used only to cap a source slice.
    source_valid_until: int | None = None


class InternalAccount(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    username: str
    password: str
    region: str
    status: Literal["active"] = "active"
    last_synced_at: int
    features: list[str] = Field(default_factory=lambda: ["shadowrocket_purchased"])
    upstream_updated_at: int | None = None
    relay_synced_at: int | None = None


class SourceSlice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_alias: str
    fetched_at: int
    valid_until: int
    accounts: list[InternalAccount]


class AggregatePool(BaseModel):
    model_config = ConfigDict(extra="forbid")

    updated_at: int
    accounts: list[InternalAccount]


class VerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=4096)


class TicketResponse(BaseModel):
    ticket: str
    expires_in: int


class RevealRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket: str = Field(min_length=32, max_length=256)
    intent: Literal["target_app", "other_app", "expert"] = "target_app"


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=8, max_length=128)
    result: Literal[
        "shadowrocket_available",
        "shadowrocket_missing",
        "login_success",
        "login_failed",
    ]


class PublicAccount(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    username: str
    password: str
    region: str
    status: Literal["active"]
    last_synced_at: int
    features: list[str]


class RevealResponse(BaseModel):
    total: int
    updated_at: int
    accounts: list[PublicAccount]
    exhausted: bool = False
    purchase_link: str | None = None
