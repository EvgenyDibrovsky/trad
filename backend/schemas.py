"""Strict webhook payload schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


SignalKind = Literal["BUY", "SELL", "NO_SIGNAL"]


class WebhookPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal[1]
    symbol: str
    signal: SignalKind
    timeframe: str | None = None
    timestamp: datetime | None = None
    entry_time: datetime | None = None
    expiry_minutes: int = Field(default=5, ge=1)
    strength: int | None = Field(default=None, ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)
    secret: str | None = None

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        return str(value).strip().upper()

    @field_validator("timeframe")
    @classmethod
    def _normalize_timeframe(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("secret")
    @classmethod
    def _normalize_secret(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("reasons")
    @classmethod
    def _normalize_reasons(cls, value: list[str]) -> list[str]:
        items = []
        for item in value:
            text = str(item).strip()
            if text:
                items.append(text)
        return items


class TestSignalPayload(WebhookPayload):
    schema_version: Literal[1] = 1
    symbol: str = "EURUSD"
    signal: SignalKind = "BUY"
