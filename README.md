# trad — сигналы TradingView (FastAPI + React + Vercel)

Веб-приложение: **TradingView Alert → webhook → FastAPI → хранилище → React UI**. Автоторговли нет.

Хранение состояния: **Upstash Redis** (REST) на проде/Vercel; без Redis данные держатся **в памяти** процесса (только для локальной отладки).

## Стек

| Часть | Технология |
|--------|------------|
| Backend | FastAPI, Mangum (Vercel serverless) |
| Frontend | React 18, Vite, TypeScript |
| Storage | Upstash Redis (`trad:settings`, `trad:signals`) |

## Структура

```
trad/
  api/index.py          # точка входа Vercel (Mangum)
  backend/              # FastAPI, логика, Redis
  frontend/             # Vite React
  requirements.txt
  vercel.json
  package.json          # build для Vercel
```

## Локальный запуск

### 1. Python API

```bash
cd trad
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Проверка: `curl http://127.0.0.1:8000/api/status`

### 2. Frontend (другой терминал)

```bash
cd trad/frontend
npm ci
npm run dev
```

Открой **http://127.0.0.1:5173** — Vite проксирует `/api` на порт **8000** (`vite.config.ts`).

### Опционально: Redis локально

Скопируйте `.env.example` → `.env` и вставьте `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` из [Upstash Console](https://console.upstash.com/). Иначе режим **memory** (данные теряются при перезапуске).

## Переменные окружения

| Переменная | Назначение |
|------------|------------|
| `UPSTASH_REDIS_REST_URL` | URL REST API Upstash |
| `UPSTASH_REDIS_REST_TOKEN` | Токен |
| `CORS_ORIGINS` | Список origin через запятую или `*` |
| `VITE_API_BASE` | (frontend build) префикс API, если фронт и API на разных доменах |

## API

| Метод | Путь |
|--------|------|
| GET | `/api/status` |
| GET | `/api/pairs` |
| POST | `/api/pairs` |
| GET | `/api/signals` |
| GET | `/api/signals/detail?symbol=EURUSD` |
| POST | `/api/webhook/tradingview` |
| POST | `/api/test-signal` |

**TradingView Webhook URL** (после деплоя):

`https://<ваш-домен-vercel>/api/webhook/tradingview`

Пример тела JSON:

```json
{
  "symbol": "EURUSD",
  "signal": "BUY",
  "timeframe": "5",
  "timestamp": "2026-04-01T15:19:59Z",
  "entry_time": "2026-04-01T15:20:00Z",
  "expiry_minutes": 5,
  "strength": 80,
  "reasons": ["Supertrend bullish flip"]
}
```

Тест без TradingView:

```bash
curl -X POST https://<host>/api/test-signal \
  -H "Content-Type: application/json" \
  -d '{"symbol":"EURUSD","signal":"BUY"}'
```

## Деплой на Vercel

1. Репозиторий подключите к [Vercel](https://vercel.com).
2. **Root directory**: корень проекта `trad`.
3. **Build Command**: `npm run build`.
4. **Output Directory**: `frontend/dist`.
5. **Install Command**: `pip install -r requirements.txt && npm --prefix frontend ci`.
6. В **Environment Variables** добавьте `UPSTASH_REDIS_REST_URL` и `UPSTASH_REDIS_REST_TOKEN`.

Файл `vercel.json` задаёт перенаправление `/api/*` на serverless-функцию `api/index.py`.

Если сборка Python не подхватывается автоматически, в настройках проекта включите **Python** для функций в каталоге `api/` (см. [Vercel Python](https://vercel.com/docs/functions/runtimes/python)).

После деплоя в TradingView укажите публичный **HTTPS** URL:  
`https://<project>.vercel.app/api/webhook/tradingview`  
(не `localhost` / `127.0.0.1`).

## Ответственность

Инструмент для личного анализа, не инвестиционный совет.
