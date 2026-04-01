"""FastAPI: API + webhook для Vercel и локального uvicorn."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import FOREX_PAIRS
from backend.state_service import (
    build_signal_payload,
    enrich_countdown,
    load_all_signals,
    load_settings,
    rows_for_api,
    save_settings,
    upsert_signal_record,
)
from backend.storage import storage_mode
from backend.symbols import validate_known_symbol

app = FastAPI(title="trad", version="2.0.0")
logger = logging.getLogger("trad.api")

_origins = os.getenv("CORS_ORIGINS", "*").strip()
if _origins == "*":
    _cors = ["*"]
else:
    _cors = [o.strip() for o in _origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/status")
def api_status() -> dict[str, Any]:
    return {
        "ok": True,
        "storage": storage_mode(),
        "pairs_count": len(FOREX_PAIRS),
    }


@app.get("/api/pairs")
def api_pairs_get() -> dict[str, Any]:
    st = load_settings()
    return {"all_pairs": FOREX_PAIRS, "settings": st}


@app.post("/api/pairs")
def api_pairs_post(body: dict[str, Any]) -> dict[str, Any]:
    save_settings(body)
    return {"ok": True, "all_pairs": FOREX_PAIRS, "settings": load_settings()}


@app.get("/api/signals")
def api_signals() -> dict[str, Any]:
    rows, settings = rows_for_api()
    return {"pairs": rows, "settings": settings}


@app.get("/api/signals/detail")
def api_signals_detail(symbol: str) -> Any:
    sym, err = validate_known_symbol(symbol)
    if err or not sym:
        return JSONResponse({"error": err or "symbol"}, status_code=400)
    rec = load_all_signals().get(sym)
    if not rec:
        return JSONResponse(
            {"error": "Нет сохранённого сигнала для этой пары.", "symbol": sym},
            status_code=404,
        )
    return enrich_countdown(dict(rec))


@app.post("/api/webhook/tradingview")
async def webhook_tradingview(request: Request) -> Any:
    raw = await request.body()
    body: dict[str, Any] = {}
    if raw:
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as e:
            return JSONResponse(
                {"ok": False, "error": "invalid_json", "message": str(e)},
                status_code=400,
            )
        if not isinstance(data, dict):
            return JSONResponse(
                {"ok": False, "error": "invalid_json", "message": "Ожидается JSON-объект"},
                status_code=400,
            )
        body = data
    else:
        form = await request.form()
        if form:
            body = dict(form)

    if not body:
        return JSONResponse(
            {
                "ok": False,
                "error": "empty_body",
                "message": "Ожидается JSON в теле запроса.",
            },
            status_code=400,
        )

    try:
        rec = build_signal_payload(body)
        sym = rec["symbol"]
        upsert_signal_record(sym, rec)
    except ValueError as e:
        msg = str(e)
        code = "validation_error"
        if "Неизвестная пара" in msg:
            code = "unknown_symbol"
        elif "signal" in msg.lower():
            code = "invalid_signal"
        elif "entry_time" in msg.lower():
            code = "invalid_entry_time"
        return JSONResponse({"ok": False, "error": code, "message": msg}, status_code=400)

    logger.info("webhook_tradingview accepted symbol=%s signal=%s", rec["symbol"], rec["signal"])
    return {
        "ok": True,
        "route": "/api/webhook/tradingview",
        "storage": storage_mode(),
        "record": enrich_countdown(rec),
    }


@app.post("/api/test-signal")
def api_test_signal(body: dict[str, Any]) -> Any:
    sig = str(body.get("signal", "BUY")).strip().upper()
    payload = {
        "symbol": body.get("symbol") or "EURUSD",
        "signal": sig,
        "timestamp": body.get("timestamp"),
        "timeframe": body.get("timeframe") or "5",
        "entry_time": body.get("entry_time"),
        "expiry_minutes": body.get("expiry_minutes", 5),
        "strength": body.get("strength", 80),
        "reasons": body.get("reasons") or ["test"],
    }
    try:
        rec = build_signal_payload(payload)
        upsert_signal_record(rec["symbol"], rec)
    except ValueError as e:
        return JSONResponse(
            {"ok": False, "error": "validation_error", "message": str(e)},
            status_code=400,
        )
    return {"ok": True, "record": enrich_countdown(rec)}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
