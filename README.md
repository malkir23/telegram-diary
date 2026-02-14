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

Or run only web service with uvicorn:

```bash
uv run uvicorn src.service.main:app --host 0.0.0.0 --port 8080
```

## Environment variables

- `TELEGRAM_BOT_TOKEN` - Telegram bot token
- `REMINDER_POLL_SECONDS` - how often bot polls due reminders
- `DATABASE_URL` - async SQLAlchemy PostgreSQL DSN
  - recommended: `postgresql+asyncpg://...`
  - also accepted: `postgresql://...` or `postgres://...` (auto-converted to `asyncpg`)

## Service API

- `GET /health`
- `POST /diary-entries`
- `POST /events`
- `PUT /events/{event_id}`
- `DELETE /events/{event_id}`
- `GET /events?user_id=<tg_user_id>`
- `POST /events/reminders/claim`

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

Service endpoint is fixed in code for local orchestration:
- `http://127.0.0.1:8080`

## Bot event commands

- `/create_event <title> | <start> | <end> | <participants>`
- `/update_event <id> | <title> | <start> | <end> | <participants>`
- `/delete_event <id>`
- `/events`

Time format: `YYYY-MM-DD HH:MM` in UTC.
Participants: comma-separated Telegram user IDs, or `-`.

If an event intersects in time with existing events for creator or participants, bot will return conflict details.
Bot also sends reminder to event creator about 1 hour before start.
When an event is created, bot sends notification to all event participants (including creator):
who created it, what was created, and event time.
