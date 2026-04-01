"""
Точка входа Vercel Serverless: ASGI через Mangum.
Локально: uvicorn backend.main:app --reload --port 8000
"""
from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from mangum import Mangum

from backend.main import app

handler = Mangum(app, lifespan="off")
