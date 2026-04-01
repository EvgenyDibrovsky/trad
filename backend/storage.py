"""
Хранилище: Upstash Redis на Vercel; in-memory для локальной разработки без Redis.
"""
from __future__ import annotations

import json
import os
from typing import Any

SETTINGS_KEY = "trad:settings"


class BaseStore:
    def get_json(self, key: str) -> Any | None:
        raise NotImplementedError

    def set_json(self, key: str, value: Any) -> None:
        raise NotImplementedError


class MemoryStore(BaseStore):
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def get_json(self, key: str) -> Any | None:
        raw = self._data.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def set_json(self, key: str, value: Any) -> None:
        self._data[key] = json.dumps(value, ensure_ascii=False)


class UpstashStore(BaseStore):
    def __init__(self, url: str, token: str) -> None:
        from upstash_redis import Redis

        self._r = Redis(url=url, token=token)

    def get_json(self, key: str) -> Any | None:
        raw = self._r.get(key)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def set_json(self, key: str, value: Any) -> None:
        self._r.set(key, json.dumps(value, ensure_ascii=False))


_store: BaseStore | None = None


def get_store() -> BaseStore:
    global _store
    if _store is not None:
        return _store
    url = os.getenv("UPSTASH_REDIS_REST_URL", "").strip()
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()
    if url and token:
        _store = UpstashStore(url, token)
    else:
        _store = MemoryStore()
    return _store


def storage_mode() -> str:
    if os.getenv("UPSTASH_REDIS_REST_URL") and os.getenv("UPSTASH_REDIS_REST_TOKEN"):
        return "upstash_redis"
    return "memory"
