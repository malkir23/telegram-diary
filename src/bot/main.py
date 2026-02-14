from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from .client import DiaryServiceClient, ServiceConflictError
from .config import settings
from .schemas import DiaryEntryCreate, EventCreate, EventDelete, EventUpdate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HELP_TEXT = (
    "Commands:\n"
    "/create_event <title> | <start> | <end> | <participants>\n"
    "/update_event <id> | <title> | <start> | <end> | <participants>\n"
    "/delete_event <id>\n"
    "/events\n\n"
    "Time format: YYYY-MM-DD HH:MM (UTC)\n"
    "Participants: comma-separated Telegram user IDs or '-'"
)


def _service_client() -> DiaryServiceClient:
    return DiaryServiceClient()


def _parse_datetime(raw: str) -> datetime:
    value = raw.strip()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _parse_participants(raw: str) -> list[int]:
    value = raw.strip()
    if value in {"", "-"}:
        return []
    result: list[int] = []
    for item in value.split(","):
        candidate = item.strip()
        if not candidate.isdigit():
            raise ValueError(f"Invalid participant id: {candidate}")
        result.append(int(candidate))
    return sorted(set(result))


def _format_conflicts(error: ServiceConflictError) -> str:
    lines = ["Conflict detected with existing events:"]
    for item in error.conflicts[:10]:
        users = ", ".join(str(user_id) for user_id in item.conflicting_user_ids)
        lines.append(
            f"- #{item.event_id} {item.title} ({item.start_at:%Y-%m-%d %H:%M} - "
            f"{item.end_at:%Y-%m-%d %H:%M}), users: {users}"
        )
    return "\n".join(lines)


async def start_handler(message: Message) -> None:
    await message.answer(
        "Send plain text to store diary entry.\nUse /help to manage events."
    )


async def help_handler(message: Message) -> None:
    await message.answer(HELP_TEXT)


async def create_event_handler(message: Message) -> None:
    if message.text is None or message.from_user is None:
        return
    raw = message.text.replace("/create_event", "", 1).strip()
    try:
        title, start_raw, end_raw, participants_raw = [
            part.strip() for part in raw.split("|", maxsplit=3)
        ]
        payload = EventCreate(
            creator_tg_user_id=message.from_user.id,
            title=title,
            start_at=_parse_datetime(start_raw),
            end_at=_parse_datetime(end_raw),
            participant_tg_user_ids=_parse_participants(participants_raw),
        )
    except Exception:
        await message.answer("Invalid format.\n" + HELP_TEXT)
        return

    try:
        async with aiohttp.ClientSession() as session:
            created = await _service_client().create_event(session, payload)
        await message.answer(
            f"Event created: #{created.id} {created.title} "
            f"{created.start_at:%Y-%m-%d %H:%M} - {created.end_at:%Y-%m-%d %H:%M} UTC"
        )
    except ServiceConflictError as conflict:
        await message.answer(_format_conflicts(conflict))
    except Exception as exc:
        logger.exception("Failed to create event")
        await message.answer(f"Failed to create event: {exc}")


async def update_event_handler(message: Message) -> None:
    if message.text is None or message.from_user is None:
        return
    raw = message.text.replace("/update_event", "", 1).strip()
    try:
        event_id_raw, title, start_raw, end_raw, participants_raw = [
            part.strip() for part in raw.split("|", maxsplit=4)
        ]
        if not event_id_raw.isdigit():
            raise ValueError("event_id")
        event_id = int(event_id_raw)
        payload = EventUpdate(
            actor_tg_user_id=message.from_user.id,
            title=title,
            start_at=_parse_datetime(start_raw),
            end_at=_parse_datetime(end_raw),
            participant_tg_user_ids=_parse_participants(participants_raw),
        )
    except Exception:
        await message.answer("Invalid format.\n" + HELP_TEXT)
        return

    try:
        async with aiohttp.ClientSession() as session:
            updated = await _service_client().update_event(session, event_id, payload)
        await message.answer(
            f"Event updated: #{updated.id} {updated.title} "
            f"{updated.start_at:%Y-%m-%d %H:%M} - {updated.end_at:%Y-%m-%d %H:%M} UTC"
        )
    except ServiceConflictError as conflict:
        await message.answer(_format_conflicts(conflict))
    except Exception as exc:
        logger.exception("Failed to update event")
        await message.answer(f"Failed to update event: {exc}")


async def delete_event_handler(message: Message) -> None:
    if message.text is None or message.from_user is None:
        return
    raw = message.text.replace("/delete_event", "", 1).strip()
    if not raw.isdigit():
        await message.answer("Usage: /delete_event <id>")
        return
    event_id = int(raw)

    try:
        async with aiohttp.ClientSession() as session:
            await _service_client().delete_event(
                session,
                event_id,
                EventDelete(actor_tg_user_id=message.from_user.id),
            )
        await message.answer(f"Event #{event_id} deleted.")
    except Exception as exc:
        logger.exception("Failed to delete event")
        await message.answer(f"Failed to delete event: {exc}")


async def list_events_handler(message: Message) -> None:
    if message.from_user is None:
        return
    try:
        async with aiohttp.ClientSession() as session:
            events = await _service_client().list_events(session, message.from_user.id)
    except Exception as exc:
        logger.exception("Failed to list events")
        await message.answer(f"Failed to list events: {exc}")
        return

    if not events:
        await message.answer("No events found.")
        return

    lines = ["Your events:"]
    for item in events[:20]:
        participants = (
            ",".join(str(user_id) for user_id in item.participant_tg_user_ids) or "-"
        )
        lines.append(
            f"#{item.id} {item.title}\n"
            f"{item.start_at:%Y-%m-%d %H:%M} - {item.end_at:%Y-%m-%d %H:%M} UTC\n"
            f"participants: {participants}"
        )
    await message.answer("\n\n".join(lines))


async def text_handler(message: Message) -> None:
    if message.text is None or message.from_user is None:
        return

    entry = DiaryEntryCreate(
        tg_user_id=message.from_user.id,
        username=message.from_user.username,
        chat_id=message.chat.id,
        message_id=message.message_id,
        text=message.text,
    )

    try:
        async with aiohttp.ClientSession() as session:
            await _service_client().save_entry(session, entry)
    except Exception as exc:
        logger.exception("Failed to save entry")
        await message.answer(f"Failed to save diary entry: {exc}")
        return

    await message.answer("Diary entry saved.")


async def reminders_loop(bot: Bot) -> None:
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                reminders = await _service_client().claim_due_reminders(session)
            for item in reminders:
                await bot.send_message(
                    item.creator_tg_user_id,
                    (
                        f"Reminder: in about 1 hour your event starts.\n"
                        f"#{item.event_id} {item.title}\n"
                        f"Start: {item.start_at:%Y-%m-%d %H:%M} UTC"
                    ),
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Reminder loop failed")
        await asyncio.sleep(max(5, settings.reminder_poll_seconds))


async def run() -> None:
    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher()

    dp.message.register(start_handler, CommandStart())
    dp.message.register(help_handler, Command("help"))
    dp.message.register(create_event_handler, Command("create_event"))
    dp.message.register(update_event_handler, Command("update_event"))
    dp.message.register(delete_event_handler, Command("delete_event"))
    dp.message.register(list_events_handler, Command("events"))
    dp.message.register(text_handler, F.text & ~F.text.startswith("/"))

    reminder_task = asyncio.create_task(reminders_loop(bot), name="reminders-loop")
    try:
        await dp.start_polling(bot)
    finally:
        reminder_task.cancel()
        await asyncio.gather(reminder_task, return_exceptions=True)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run())
