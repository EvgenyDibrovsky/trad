"""Бизнес-логика: настройки и сигналы в хранилище."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from backend.config import FOREX_PAIRS
from backend.schemas import WebhookPayload
from backend.storage import SETTINGS_KEY, get_store
from backend.symbols import validate_known_symbol

DEFAULT_SETTINGS: dict[str, Any] = {
    "selected_pairs": [FOREX_PAIRS[0]],
    "show_all_pairs": True,
}

SIGNALS_KEY = "trad:signals"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _utc_now_iso() -> str:
    return _utc_now().strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _coerce_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    dt = value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(microsecond=0)


def _fmt_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    dt = _coerce_utc(value)
    if dt is None:
        return None
    assert dt is not None
    return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _parse_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _coerce_utc(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _coerce_utc(parsed)


def _resolve_expires_at(rec: dict[str, Any]) -> datetime | None:
    expires = _parse_utc(rec.get("signal_expires_at"))
    if expires is not None:
        return expires
    entry = _parse_utc(rec.get("entry_at") or rec.get("entry_time"))
    if entry is None:
        return None
    exp = rec.get("expiry_minutes")
    try:
        expiry_minutes = int(exp) if exp is not None else None
    except (TypeError, ValueError):
        expiry_minutes = None
    if expiry_minutes is None:
        return None
    return entry + timedelta(minutes=expiry_minutes)


def load_settings() -> dict[str, Any]:
    st = get_store().get_json(SETTINGS_KEY)
    if not isinstance(st, dict):
        st = dict(DEFAULT_SETTINGS)
    out = {**DEFAULT_SETTINGS, **st}
    sel = out.get("selected_pairs")
    if not isinstance(sel, list):
        sel = []
    out["selected_pairs"] = [
        str(x).strip().upper()
        for x in sel
        if str(x).strip().upper() in FOREX_PAIRS
    ] or [FOREX_PAIRS[0]]
    out["show_all_pairs"] = bool(out.get("show_all_pairs", True))
    return out


def save_settings(data: dict[str, Any]) -> dict[str, Any]:
    cur = load_settings()
    if "selected_pairs" in data and isinstance(data["selected_pairs"], list):
        validated: list[str] = []
        for x in data["selected_pairs"]:
            sym, _ = validate_known_symbol(str(x))
            if sym:
                validated.append(sym)
        cur["selected_pairs"] = validated or [FOREX_PAIRS[0]]
    if "show_all_pairs" in data:
        cur["show_all_pairs"] = bool(data["show_all_pairs"])
    get_store().set_json(SETTINGS_KEY, cur)
    return cur


def load_all_signals() -> dict[str, dict[str, Any]]:
    raw = get_store().get_json(SIGNALS_KEY)
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            out[str(k).upper()] = v
    return out


def save_all_signals(signals: dict[str, dict[str, Any]]) -> None:
    get_store().set_json(SIGNALS_KEY, signals)


def upsert_signal_record(symbol: str, record: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    signals = load_all_signals()
    existing = signals.get(symbol)
    if existing and existing.get("last_event_id") == record.get("last_event_id"):
        return existing, True
    signals[symbol] = record
    save_all_signals(signals)
    return record, False


def map_signal(raw: str) -> str:
    s = str(raw).strip().upper()
    if s in ("BUY", "LONG", "CALL"):
        return "BUY"
    if s in ("SELL", "SHORT", "PUT"):
        return "SELL"
    if s in ("NO_SIGNAL", "NONE", "NEUTRAL", "FLAT", ""):
        return "NO_SIGNAL"
    raise ValueError(f"signal должен быть BUY, SELL или NO_SIGNAL; получено: {raw!r}")


def build_signal_payload(payload: WebhookPayload, source: str = "webhook") -> dict[str, Any]:
    sym, err = validate_known_symbol(payload.symbol)
    if err or not sym:
        raise ValueError(err or "symbol invalid")

    sig = map_signal(payload.signal)

    now_utc = _utc_now()
    timestamp_utc = _coerce_utc(payload.timestamp) or now_utc
    entry_utc = _coerce_utc(payload.entry_time) or timestamp_utc or now_utc
    signal_expires_at = entry_utc + timedelta(minutes=payload.expiry_minutes)
    event_id = f"{sym}:{sig}:{_fmt_utc(timestamp_utc)}"

    reasons_list = list(payload.reasons)

    rec: dict[str, Any] = {
        "schema_version": payload.schema_version,
        "symbol": sym,
        "signal": sig,
        "ui_status": sig,
        "entry_time": _fmt_utc(entry_utc),
        "entry_at": _fmt_utc(entry_utc),
        "expiry_minutes": payload.expiry_minutes,
        "signal_expires_at": _fmt_utc(signal_expires_at),
        "timeframe": payload.timeframe,
        "strength": payload.strength,
        "reasons": reasons_list,
        "timestamp": _fmt_utc(timestamp_utc),
        "updated_at": _utc_now_iso(),
        "source": source,
        "last_event_id": event_id,
    }
    return rec


def enrich_countdown(rec: dict[str, Any]) -> dict[str, Any]:
    out = dict(rec)
    expires = _resolve_expires_at(out)
    now = _utc_now()
    if out.get("ui_status") in ("BUY", "SELL") and expires is not None:
        remaining = int((expires - now).total_seconds())
        out["countdown_seconds"] = max(0, remaining)
        if remaining <= 0:
            out["ui_status"] = "NO_SIGNAL"
            out["signal"] = "NO_SIGNAL"
    else:
        out["countdown_seconds"] = None
    return out


def signal_is_active(rec: dict[str, Any]) -> bool:
    status = str(rec.get("ui_status") or rec.get("signal") or "NO_SIGNAL").upper()
    if status not in ("BUY", "SELL"):
        return False
    expires = _resolve_expires_at(rec)
    if expires is None:
        return False
    return _utc_now() < expires


def row_for_signal(symbol: str, rec: dict[str, Any] | None, selected: bool = True) -> dict[str, Any]:
    if not rec:
        return {
            "symbol": symbol,
            "selected": selected,
            "ui_status": "NO_SIGNAL",
            "label": "NO SIGNAL",
            "signal": "NO_SIGNAL",
            "entry_time": None,
            "expiry_minutes": None,
            "updated_at": None,
            "timeframe": None,
            "strength": None,
            "reasons": [],
            "signal_expires_at": None,
            "countdown_seconds": None,
        }

    ui_status = str(rec.get("ui_status") or rec.get("signal") or "NO_SIGNAL").upper()
    if not signal_is_active(rec):
        return {
            "symbol": symbol,
            "selected": selected,
            "ui_status": "NO_SIGNAL",
            "label": "NO SIGNAL",
            "signal": "NO_SIGNAL",
            "entry_time": rec.get("entry_time"),
            "expiry_minutes": rec.get("expiry_minutes"),
            "updated_at": rec.get("updated_at"),
            "timeframe": rec.get("timeframe"),
            "strength": rec.get("strength"),
            "reasons": rec.get("reasons", []),
            "signal_expires_at": rec.get("signal_expires_at"),
            "countdown_seconds": None,
            "schema_version": rec.get("schema_version"),
            "last_event_id": rec.get("last_event_id"),
        }

    merged = {**rec, "ui_status": ui_status, "selected": selected}
    return enrich_countdown(merged)


def rows_for_api() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    settings = load_settings()
    selected = set(settings.get("selected_pairs") or [FOREX_PAIRS[0]])
    show_all = bool(settings.get("show_all_pairs", True))
    signals = load_all_signals()

    if show_all:
        symbols = list(FOREX_PAIRS)
    else:
        symbols = sorted(selected)

    rows: list[dict[str, Any]] = []
    for sym in symbols:
        sel = sym in selected
        rec = signals.get(sym)
        rows.append(row_for_signal(sym, rec, selected=sel))

    return rows, settings
