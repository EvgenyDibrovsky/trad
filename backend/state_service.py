"""Бизнес-логика: настройки и сигналы в хранилище."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.config import FOREX_PAIRS
from backend.storage import SETTINGS_KEY, get_store
from backend.symbols import validate_known_symbol

DEFAULT_SETTINGS: dict[str, Any] = {
    "selected_pairs": [],
    "show_all_pairs": True,
}

SIGNALS_KEY = "trad:signals"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def load_settings() -> dict[str, Any]:
    st = get_store().get_json(SETTINGS_KEY)
    if not isinstance(st, dict):
        st = dict(DEFAULT_SETTINGS)
    out = {**DEFAULT_SETTINGS, **st}
    sel = out.get("selected_pairs")
    if not isinstance(sel, list):
        sel = []
    out["selected_pairs"] = [str(x).strip().upper() for x in sel if str(x).strip()]
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
        cur["selected_pairs"] = validated
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


def upsert_signal_record(symbol: str, record: dict[str, Any]) -> dict[str, Any]:
    signals = load_all_signals()
    signals[symbol] = record
    save_all_signals(signals)
    return record


def map_signal(raw: str) -> str:
    s = str(raw).strip().upper()
    if s in ("BUY", "LONG", "CALL"):
        return "BUY"
    if s in ("SELL", "SHORT", "PUT"):
        return "SELL"
    if s in ("NO_SIGNAL", "NONE", "NEUTRAL", "FLAT", ""):
        return "NO_SIGNAL"
    raise ValueError(f"signal должен быть BUY, SELL или NO_SIGNAL; получено: {raw!r}")


def parse_time(s: Any) -> tuple[str | None, str | None]:
    """Возвращает (iso_utc, error)."""
    if s is None:
        return None, None
    text = str(s).strip()
    if not text:
        return None, None
    z = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(z)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00"), None
    except (TypeError, ValueError):
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(text[:19], fmt).replace(tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00"), None
        except ValueError:
            continue
    return None, f"не удалось распарсить время: {text!r}"


def build_signal_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sym, err = validate_known_symbol(str(payload.get("symbol", "")))
    if err or not sym:
        raise ValueError(err or "symbol invalid")

    sig = map_signal(str(payload.get("signal", "NO_SIGNAL")))

    entry_raw = payload.get("entry_time") or payload.get("entry_at")
    entry_iso: str | None = None
    if entry_raw is not None and str(entry_raw).strip():
        entry_iso, eerr = parse_time(entry_raw)
        if eerr:
            raise ValueError(f"entry_time: {eerr}")

    ts_raw = payload.get("timestamp") or payload.get("time")
    ts_iso, ts_warn = (None, None)
    if ts_raw is not None and str(ts_raw).strip():
        ts_iso, ts_warn = parse_time(ts_raw)

    if not entry_iso:
        entry_iso = _utc_now_iso()

    exp = payload.get("expiry_minutes")
    try:
        expiry_minutes = int(exp) if exp is not None else 5
    except (TypeError, ValueError):
        expiry_minutes = 5

    tf = payload.get("timeframe") or payload.get("interval")
    timeframe = str(tf).strip() if tf is not None else None

    st = payload.get("strength")
    try:
        strength = int(st) if st is not None else None
    except (TypeError, ValueError):
        strength = None

    reasons = payload.get("reasons")
    if isinstance(reasons, str):
        reasons_list = [x.strip() for x in reasons.split(";") if x.strip()]
    elif isinstance(reasons, list):
        reasons_list = [str(x) for x in reasons]
    else:
        reasons_list = []

    rec: dict[str, Any] = {
        "symbol": sym,
        "signal": sig,
        "ui_status": sig,
        "entry_time": entry_iso,
        "entry_at": entry_iso,
        "expiry_minutes": expiry_minutes,
        "timeframe": timeframe,
        "strength": strength,
        "reasons": reasons_list,
        "timestamp": ts_iso,
        "timestamp_raw": str(ts_raw).strip() if ts_raw is not None else None,
        "timestamp_parse_warning": ts_warn,
        "updated_at": _utc_now_iso(),
        "source": "webhook",
    }
    return rec


def enrich_countdown(rec: dict[str, Any]) -> dict[str, Any]:
    out = dict(rec)
    ea = out.get("entry_at") or out.get("entry_time")
    if ea and out.get("ui_status") in ("BUY", "SELL"):
        try:
            entry = datetime.fromisoformat(str(ea).replace("Z", "+00:00"))
            if entry.tzinfo is None:
                entry = entry.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            out["countdown_seconds"] = max(0, int((entry - now).total_seconds()))
        except (TypeError, ValueError):
            out["countdown_seconds"] = None
    else:
        out["countdown_seconds"] = None
    return out


def rows_for_api() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    settings = load_settings()
    selected = set(settings.get("selected_pairs") or [])
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
        if not sel:
            rows.append(
                {
                    "symbol": sym,
                    "selected": False,
                    "ui_status": "OFF",
                    "label": "—",
                    "signal": None,
                    "entry_time": None,
                    "expiry_minutes": None,
                    "updated_at": None,
                    "timeframe": None,
                    "strength": None,
                    "reasons": [],
                    "countdown_seconds": None,
                }
            )
            continue

        if not rec:
            rows.append(
                {
                    "symbol": sym,
                    "selected": True,
                    "ui_status": "NO_SIGNAL",
                    "label": "NO SIGNAL",
                    "signal": "NO_SIGNAL",
                    "entry_time": None,
                    "expiry_minutes": None,
                    "updated_at": None,
                    "timeframe": None,
                    "strength": None,
                    "reasons": [],
                    "countdown_seconds": None,
                }
            )
            continue

        ui = rec.get("ui_status") or rec.get("signal") or "NO_SIGNAL"
        merged = {**rec, "ui_status": ui, "selected": True}
        rows.append(enrich_countdown(merged))

    return rows, settings
