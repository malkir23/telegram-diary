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
- `POST /events/{event_id}/reminder-sent`
- `GET /users/{user_id}/timezone`
- `PUT /users/{user_id}/timezone`

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
- `/events_today`
- `/set_timezone <IANA timezone>`
- `/timezone`

Time format: `YYYY-MM-DD HH:MM` in your configured timezone.
Participants: comma-separated tags/names (for example: `@alice,bob smith`), or `-`.

`start_at` and `end_at` are converted to UTC before storing in database.
When events are shown back to user, time is converted from UTC to user's timezone.

If an event intersects in time with existing events for creator or participants, bot will return conflict details.
Bot sends reminder to event creator about 10 minutes before start.
Reminder is marked as sent only after successful Telegram delivery.
When an event is created, bot sends notification to all event participants (including creator):
who created it, what was created, and event time.
For participants by name/tag, direct notification works when that alias is known to bot from prior interaction.
`start_at` for create/update must be >= current time.
