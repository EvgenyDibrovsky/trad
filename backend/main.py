"""FastAPI: API + webhook для Vercel и локального uvicorn."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

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
from backend.schemas import TestSignalPayload, WebhookPayload
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


def json_error(status_code: int, error: str, message: str, **extra: Any) -> JSONResponse:
    payload: dict[str, Any] = {"ok": False, "error": error, "message": message}
    payload.update(extra)
    return JSONResponse(payload, status_code=status_code)


def webhook_secret() -> str:
    secret = os.getenv("WEBHOOK_SECRET", "").strip()
    if not secret:
        raise RuntimeError("WEBHOOK_SECRET is not configured.")
    return secret


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 404:
        return json_error(404, "not_found", "Unknown route.")
    return json_error(exc.status_code, "http_error", str(exc.detail))


@app.exception_handler(RequestValidationError)
async def request_validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return json_error(422, "invalid_payload", "Request validation failed.", details=exc.errors())


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled error: %s", exc)
    return json_error(500, "internal_error", "Internal server error.")


@app.get("/api/status")
def api_status() -> dict[str, Any]:
    return {
        "ok": True,
        "storage": storage_mode(),
        "pairs_count": len(FOREX_PAIRS),
        "webhook_secret_configured": bool(os.getenv("WEBHOOK_SECRET", "").strip()),
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
        return json_error(400, "invalid_symbol", err or "symbol")
    rec = load_all_signals().get(sym)
    if not rec:
        return json_error(404, "not_found", "No saved signal for this pair.", symbol=sym)
    return {"ok": True, "record": enrich_countdown(dict(rec))}


@app.post("/api/webhook/tradingview")
async def webhook_tradingview(request: Request) -> Any:
    raw = await request.body()
    if raw:
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as e:
            return json_error(400, "invalid_json", str(e))
        if not isinstance(data, dict):
            return json_error(400, "invalid_json", "Expected JSON object.")
        body = data
    else:
        form = await request.form()
        if form:
            body = dict(form)
        else:
            body = {}

    if not body:
        return json_error(400, "empty_body", "Expected JSON body.")

    configured_secret = None
    try:
        configured_secret = webhook_secret()
    except RuntimeError as e:
        return json_error(500, "webhook_secret_not_configured", str(e))

    received_secret = request.headers.get("X-Webhook-Secret") or str(body.get("secret") or "").strip()
    if not received_secret or received_secret != configured_secret:
        return json_error(401, "unauthorized_webhook", "Invalid or missing webhook secret.")

    try:
        payload = WebhookPayload.model_validate(body)
    except ValidationError as e:
        return json_error(422, "invalid_payload", "Webhook payload failed validation.", details=e.errors())

    try:
        rec = build_signal_payload(payload)
        sym = rec["symbol"]
        saved, deduped = upsert_signal_record(sym, rec)
    except ValueError as e:
        msg = str(e)
        code = "validation_error"
        if "Неизвестная пара" in msg:
            code = "unknown_symbol"
        elif "signal" in msg.lower():
            code = "invalid_signal"
        elif "entry_time" in msg.lower():
            code = "invalid_entry_time"
        return json_error(400, code, msg)

    if not deduped:
        logger.info("webhook_tradingview accepted symbol=%s signal=%s", saved["symbol"], saved["signal"])
    return {
        "ok": True,
        "route": "/api/webhook/tradingview",
        "storage": storage_mode(),
        "deduped": deduped,
        "record": saved,
    }


@app.post("/api/test-signal")
def api_test_signal(body: dict[str, Any]) -> Any:
    try:
        payload = TestSignalPayload.model_validate(body)
    except ValidationError as e:
        return json_error(422, "invalid_payload", "Test payload failed validation.", details=e.errors())

    try:
        rec = build_signal_payload(payload, source="test")
        saved, deduped = upsert_signal_record(rec["symbol"], rec)
    except ValueError as e:
        return json_error(400, "validation_error", str(e))
    return {"ok": True, "deduped": deduped, "record": saved}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
