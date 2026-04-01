"""Нормализация тикеров: OANDA:EURUSD, EUR/USD -> EURUSD."""
from __future__ import annotations

import re

from backend.config import ALLOWED_SYMBOLS


def normalize_symbol(raw: str) -> str:
    if not raw or not str(raw).strip():
        return ""
    s = str(raw).strip().upper()
    s = s.split(":")[-1].strip()
    s = s.replace(" ", "").replace("-", "")
    if "/" in s:
        parts = [p for p in s.split("/") if p]
        if len(parts) >= 2 and len(parts[0]) >= 3 and len(parts[1]) >= 3:
            s = parts[0][:3] + parts[1][:3]
    s = re.sub(r"[^A-Z]", "", s)
    if len(s) == 6:
        return s
    return re.sub(r"[^A-Z0-9]", "", str(raw).strip().upper())


def validate_known_symbol(sym: str) -> tuple[str | None, str | None]:
    """Возвращает (symbol, error_message)."""
    n = normalize_symbol(sym)
    if not n:
        return None, "symbol обязателен"
    if n not in ALLOWED_SYMBOLS:
        return None, f"Неизвестная пара: {n}. Используйте символ из списка приложения."
    return n, None
