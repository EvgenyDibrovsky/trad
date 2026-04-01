"""Централизованный список пар и настройки."""
from __future__ import annotations

FOREX_PAIRS: list[str] = [
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "USDCHF",
    "EURJPY",
    "GBPJPY",
    "EURCHF",
    "EURAUD",
    "EURCAD",
    "AUDUSD",
    "AUDJPY",
    "AUDCAD",
    "AUDCHF",
    "CADJPY",
    "CADCHF",
    "GBPCHF",
    "GBPAUD",
    "GBPCAD",
    "CHFJPY",
]

ALLOWED_SYMBOLS: frozenset[str] = frozenset(FOREX_PAIRS)
