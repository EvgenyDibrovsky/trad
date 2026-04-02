"""Централизованный список пар и настройки."""
from __future__ import annotations

FOREX_PAIRS: list[str] = ["EURUSD"]

ALLOWED_SYMBOLS: frozenset[str] = frozenset(FOREX_PAIRS)
