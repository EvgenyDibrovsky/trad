# trad — сигналы TradingView (FastAPI + React + Vercel)

Веб-приложение: **TradingView Alert → webhook → FastAPI → хранилище → React UI**. Автоторговли нет.

Сейчас проект временно настроен только на одну пару: `EURUSD`. Позже список пар можно расширить снова в `backend/config.py`.

## Кратко

Проект принимает сигнал из TradingView, сохраняет его в Redis и показывает его в UI.

Сейчас интерфейс и API упрощены под одну пару:
- `EURUSD`
- один checkbox для `EURUSD`
- одна строка в таблице

## Как это работает

1. TradingView отправляет webhook.
2. Backend проверяет `symbol` и `signal`.
3. Символ нормализуется, например `OANDA:EURUSD` -> `EURUSD`.
4. Данные сохраняются в Upstash Redis.
5. Frontend опрашивает API и показывает текущее состояние.

## Где сейчас ограничение

- `backend/config.py` содержит только `FOREX_PAIRS = ["EURUSD"]`
- `/api/pairs`, `/api/signals`, `/api/test-signal` работают только с `EURUSD`
- UI показывает только `EURUSD`

## Webhook security

Webhook защищён секретом `WEBHOOK_SECRET`.

Backend принимает секрет одним из способов:
- заголовок `X-Webhook-Secret`
- поле `secret` в JSON body

Если секрет отсутствует или неверный, webhook возвращает `401` и ничего не сохраняет.
Если `WEBHOOK_SECRET` не задан, webhook возвращает `500` как ошибка конфигурации.

## Webhook payload

Поддерживаемый JSON:

```json
{
  "schema_version": 1,
  "symbol": "EURUSD",
  "signal": "BUY",
  "timeframe": "5",
  "timestamp": "2026-04-01T15:19:59Z",
  "entry_time": "2026-04-01T15:20:00Z",
  "expiry_minutes": 5,
  "strength": 80,
  "reasons": ["Supertrend bullish flip"],
  "secret": "optional"
}
```

Обязательные поля:
- `schema_version` = `1`
- `symbol`
- `signal` (`BUY`, `SELL`, `NO_SIGNAL`)

Необязательные поля:
- `timeframe`
- `timestamp`
- `entry_time`
- `expiry_minutes`
- `strength`
- `reasons`
- `secret`

Если payload не проходит проверку, backend возвращает `422` JSON с описанием ошибок.

## Payload examples

BUY:

```json
{
  "schema_version": 1,
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

SELL:

```json
{
  "schema_version": 1,
  "symbol": "EURUSD",
  "signal": "SELL",
  "timeframe": "5",
  "timestamp": "2026-04-01T15:19:59Z",
  "entry_time": "2026-04-01T15:20:00Z",
  "expiry_minutes": 5,
  "strength": 75,
  "reasons": ["Supertrend bearish flip"]
}
```

NO_SIGNAL:

```json
{
  "schema_version": 1,
  "symbol": "EURUSD",
  "signal": "NO_SIGNAL",
  "timeframe": "5",
  "timestamp": "2026-04-01T15:19:59Z",
  "entry_time": "2026-04-01T15:20:00Z",
  "expiry_minutes": 5,
  "reasons": ["Flat market"]
}
```

## Time handling

- Backend хранит все timestamps в UTC.
- Входные timestamps парсятся как ISO 8601.
- Поддерживается `Z`.
- Если `entry_time` не пришёл, backend берёт `timestamp`, а если его тоже нет, использует текущее UTC-время.
- `signal_expires_at` считается как `entry_time + expiry_minutes`.
- Если сигнал уже истёк, он больше не отображается как `BUY/SELL`, а показывается как `NO_SIGNAL`.

## Frontend fallback

- Если API недоступен, UI показывает статус `Backend unavailable`.
- Если `entry_time` отсутствует, UI не ломается и показывает `—`.
- Countdown не уходит в минус: после истечения сигнал становится `NO_SIGNAL`.

## Deduplication

Если приходит тот же `symbol + signal + timestamp`, backend не перезаписывает сигнал повторно и возвращает `deduped: true`.

## API errors

Все ошибки возвращаются JSON-ом.

| Код | Значение |
|-----|----------|
| `200` | success |
| `400` | bad request |
| `401` | unauthorized webhook |
| `404` | unknown route / missing signal |
| `422` | invalid payload |
| `500` | internal error |

Хранение состояния: **Upstash Redis** (REST) на проде/Vercel.

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

### Redis обязательно

Скопируйте `.env.example` → `.env` и вставьте `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` из [Upstash Console](https://console.upstash.com/).

## Переменные окружения

| Переменная | Назначение |
|------------|------------|
| `UPSTASH_REDIS_REST_URL` | URL REST API Upstash |
| `UPSTASH_REDIS_REST_TOKEN` | Токен |
| `WEBHOOK_SECRET` | Секрет webhook |
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

`https://trad.vercel.app/api/webhook/tradingview`

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
  -d '{"schema_version":1,"symbol":"EURUSD","signal":"BUY","timeframe":"5","expiry_minutes":5,"strength":80,"reasons":["test"]}'
```

`/api/test-signal` принимает тот же контракт, что и production webhook, но `symbol` по умолчанию `EURUSD`.

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
`https://trad.vercel.app/api/webhook/tradingview`  
(не `localhost` / `127.0.0.1`).

### Webhook response

При успешном приёме webhook backend возвращает JSON с `route: "/api/webhook/tradingview"` и `storage: "upstash_redis"`.

## Redis model

Ключи:
- `trad:settings`
- `trad:signals`

В `trad:signals` хранятся поля:
- `schema_version`
- `symbol`
- `signal`
- `entry_time`
- `entry_at`
- `timestamp`
- `signal_expires_at`
- `expiry_minutes`
- `strength`
- `reasons`
- `updated_at`
- `last_event_id`

## Где расширять пары

Когда понадобится вернуть несколько символов, начните с `backend/config.py` и списка `FOREX_PAIRS`.

## Ответственность

Инструмент для личного анализа, не инвестиционный совет.
