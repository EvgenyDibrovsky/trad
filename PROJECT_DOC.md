# trad: документация логики проекта

## Что это

`trad` - это приложение для приёма TradingView webhook-сигналов, их нормализации, хранения и отображения в UI.

Сейчас проект временно работает только с одной парой: `EURUSD`.

## Главная идея

1. TradingView отправляет webhook.
2. Backend проверяет `symbol` и `signal`.
3. `symbol` нормализуется, например `OANDA:EURUSD` -> `EURUSD`.
4. Сигнал сохраняется в Redis.
5. Frontend читает состояние через API и показывает одну строку `EURUSD`.

## Компоненты

- `api/index.py` - entrypoint для Vercel.
- `backend/main.py` - FastAPI endpoints.
- `backend/schemas.py` - strict Pydantic contracts.
- `backend/state_service.py` - логика настроек, сигналов, countdown.
- `backend/symbols.py` - нормализация и валидация symbol.
- `backend/config.py` - разрешённые пары.
- `backend/storage.py` - Upstash Redis storage layer.
- `frontend/src/App.tsx` - UI.
- `frontend/src/App.css` - стили и blinking state.

## Текущая конфигурация

- Разрешённая пара: `EURUSD`
- `FOREX_PAIRS = ["EURUSD"]`
- API endpoints работают только с `EURUSD`
- UI показывает только `EURUSD`

## Webhook security

- Секрет хранится в `WEBHOOK_SECRET`
- Backend принимает секрет через `X-Webhook-Secret` или поле `secret` в JSON body
- Если секрет неверный или отсутствует, webhook отвечает `401`
- При `401` сигнал не сохраняется
- Если `WEBHOOK_SECRET` не задан, webhook отвечает `500` как ошибка конфигурации

## Payload contract

Поддерживаемый webhook JSON:

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

Обязательные поля:
- `schema_version = 1`
- `symbol`
- `signal`

Необязательные поля:
- `timeframe`
- `timestamp`
- `entry_time`
- `expiry_minutes`
- `strength`
- `reasons`
- `secret`

Validation делается через Pydantic.

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

## UTC time handling

- Все timestamps в backend хранятся в UTC
- ISO 8601 поддерживается, включая `Z`
- Если `entry_time` не пришёл, backend использует `timestamp`
- Если нет и `timestamp`, backend ставит текущее UTC время
- `signal_expires_at = entry_time + expiry_minutes`
- Если сигнал уже истёк, UI больше не показывает `BUY/SELL`, а переводит строку в `NO_SIGNAL`

## Deduplication

- Дедуп-ключ: `symbol + signal + timestamp`
- Если приходит тот же набор ещё раз, Redis-значение не переписывается
- UI не дёргается повторно

## API responses

Backend возвращает JSON с понятными кодами:
- `200` success
- `400` bad request
- `401` unauthorized webhook
- `404` unknown route / missing signal
- `422` invalid payload
- `500` internal error

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

## Как работает backend

### 1. `/api/status`
Возвращает:
- `ok`
- режим хранилища
- количество пар
- `webhook_secret_configured`

### 2. `/api/pairs`
Возвращает:
- `all_pairs`
- `settings`

Настройки сейчас сохраняются, но фактически проект ограничен одной парой.

### 3. `/api/signals`
Собирает строки для UI:
- если пара выбрана, показывает её сигнал
- если сигнала нет, показывает `NO_SIGNAL`
- если сигнал есть, добавляет countdown

### 4. `/api/signals/detail`
Отдаёт полный сохранённый сигнал по symbol.

### 5. `/api/webhook/tradingview`
Основной входной endpoint.

Логика:
- принять JSON или form body
- распарсить payload
- нормализовать symbol
- проверить, что symbol разрешён
- привести signal к `BUY`, `SELL` или `NO_SIGNAL`
- сохранить запись в Redis

### 6. `/api/test-signal`
Тестовый endpoint для ручной проверки.

Он всегда работает с `EURUSD`.

## Нормализация symbol

Backend приводит входные значения к единому виду.

Примеры:
- `OANDA:EURUSD` -> `EURUSD`
- `EUR/USD` -> `EURUSD`

После нормализации идёт проверка по `ALLOWED_SYMBOLS`.

## Хранилище

Используется Upstash Redis.

Ключи:
- `trad:settings`
- `trad:signals`

Если Redis не настроен, backend выдаёт ошибку конфигурации.

## Как работает frontend

UI сейчас упрощён до одной строки `EURUSD`.

Показываются:
- `signal`
- `entry time`
- `expiry`
- `countdown`
- `last update`
- blinking `BUY` / `SELL` state

Frontend:
- запрашивает `/api/pairs`
- запрашивает `/api/signals`
- обновляет данные каждые 2.5 секунды
- использует `EURUSD` для тестовых сигналов
- если API недоступен, показывает `Backend unavailable`

## Логика отображения

1. Если сигнал `BUY` или `SELL`, строка подсвечивается.
2. Если сигнала нет, показывается `NO SIGNAL`.
3. Если пара не выбрана, показывается `—`.
4. Countdown считается по времени `entry_at` / `entry_time`.

## Поток данных

```text
TradingView webhook
  -> backend/main.py
  -> backend/schemas.py
  -> backend/state_service.py
  -> backend/symbols.py
  -> backend/storage.py
  -> Upstash Redis
  -> /api/signals
  -> frontend/src/App.tsx
```

## ASCII-схема работы

```text
┌───────────────┐
│ TradingView    │
│ webhook alert  │
└───────┬───────┘
        │ POST /api/webhook/tradingview
        v
┌────────────────────────────┐
│ backend/main.py             │
│ - принимает request         │
│ - валидирует payload       │
│ - вызывает build_signal... │
└───────┬────────────────────┘
        │
        v
┌────────────────────────────┐
│ backend/symbols.py          │
│ - normalize_symbol()        │
│ - validate_known_symbol()   │
└───────┬────────────────────┘
        │ EURUSD only
        v
┌────────────────────────────┐
│ backend/state_service.py    │
│ - map_signal()              │
│ - build_signal_payload()    │
│ - signal_is_active()        │
│ - upsert_signal_record()    │
└───────┬────────────────────┘
        │
        v
┌────────────────────────────┐
│ backend/storage.py          │
│ - Upstash Redis             │
│ - trad:settings             │
│ - trad:signals              │
└───────┬────────────────────┘
        │
        v
┌────────────────────────────┐
│ /api/signals                │
│ - rows_for_api()            │
│ - enrich_countdown()        │
└───────┬────────────────────┘
        │
        v
┌────────────────────────────┐
│ frontend/src/App.tsx        │
│ - polls API                 │
│ - renders one EURUSD row    │
│ - shows BUY/SELL state      │
└────────────────────────────┘
```

## Ментальная карта логики

```text
trad
├── Вход
│   ├── TradingView webhook
│   ├── Test signal button
│   └── API requests from UI
├── Backend logic
│   ├── normalize symbol
│   ├── validate allowed pair
│   ├── map signal to BUY/SELL/NO_SIGNAL
│   ├── parse time fields
│   ├── build signal payload
│   ├── calculate countdown
│   └── persist record
├── Storage
│   ├── trad:settings
│   └── trad:signals
├── API
│   ├── /api/status
│   ├── /api/pairs
│   ├── /api/signals
│   ├── /api/signals/detail
│   ├── /api/webhook/tradingview
│   └── /api/test-signal
├── Frontend logic
│   ├── load settings
│   ├── poll signals
│   ├── render one EURUSD row
│   ├── show blinking BUY/SELL
│   ├── show entry time
│   ├── show expiry
│   ├── show countdown
│   └── show last update
└── Expansion points
    ├── backend/config.py
    ├── backend/state_service.py
    └── frontend/src/App.tsx
```

## Где расширять обратно

- `backend/config.py` - добавить новые пары в `FOREX_PAIRS`
- `backend/state_service.py` - адаптировать defaults и filtering
- `frontend/src/App.tsx` - вернуть список пар в UI

## Краткий вывод

Сейчас проект - это однопарный pipeline для `EURUSD`: webhook -> validation -> storage -> UI.
