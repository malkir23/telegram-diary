# Telegram Diary

Asynchronous Telegram bot that sends messages to a separate web service.
The web service asynchronously stores data in PostgreSQL.

## Stack

- `uv` for environment and dependency management
- `aiogram` for Telegram bot
- `aiohttp` for web service (no FastAPI)
- `SQLAlchemy async` + `asyncpg` for PostgreSQL

## Quick start

1. Install dependencies:

```bash
uv sync
```

2. Create `.env` from example:

```bash
copy .env.example .env
```

3. Run everything with one handler (migrations + service + bot):

```bash
uv run python main.py
```

## Environment variables

- `TELEGRAM_BOT_TOKEN` - Telegram bot token
- `DIARY_SERVICE_URL` - web service URL, e.g. `http://localhost:8080`
- `DIARY_SERVICE_API_KEY` - key used by bot
- `SERVICE_API_KEY` - expected key on web service (`X-API-Key`)
- `DATABASE_URL` - async SQLAlchemy PostgreSQL DSN
  - recommended: `postgresql+asyncpg://...`
  - also accepted: `postgresql://...` or `postgres://...` (auto-converted to `asyncpg`)

## Service API

- `GET /health`
- `POST /diary-entries`

Payload example:

```json
{
  "tg_user_id": 123456,
  "username": "user_name",
  "chat_id": 123456,
  "message_id": 42,
  "text": "My diary entry"
}
```

## Startup flow

`main.py` uses `ApplicationHandler` (`src/handler.py`):

1. Runs `alembic upgrade head`
2. Starts `aiohttp` service
3. Starts Telegram bot
4. Writes lifecycle logs for migrations and tasks
