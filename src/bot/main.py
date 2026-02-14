from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
    "/set_timezone <IANA timezone>  (example: Europe/Kyiv)\n"
    "/timezone\n"
    "/create_event <title> | <start> | <end> | <participants>\n"
    "/update_event <id> | <title> | <start> | <end> | <participants>\n"
    "/delete_event <id>\n"
    "/events\n\n"
    "/events_today\n\n"
    "Time format: YYYY-MM-DD HH:MM (in your timezone)\n"
    "Participants: comma-separated tags/names or '-'"
)

KNOWN_USERS: dict[str, int] = {}


def _service_client() -> DiaryServiceClient:
    return DiaryServiceClient()


def _normalize_participant_label(value: str) -> str:
    candidate = value.strip()
    if candidate.startswith("@"):
        candidate = candidate[1:]
    return candidate.casefold()


def _register_user_aliases(message: Message) -> None:
    if message.from_user is None:
        return
    if message.from_user.username:
        KNOWN_USERS[_normalize_participant_label(message.from_user.username)] = (
            message.from_user.id
        )
    full_name = message.from_user.full_name.strip()
    if full_name:
        KNOWN_USERS[_normalize_participant_label(full_name)] = message.from_user.id


def _parse_local_datetime(raw: str, timezone: str) -> datetime:
    value = raw.strip()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M")

    tz = ZoneInfo(timezone)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(UTC)


def _parse_participants(raw: str) -> list[str]:
    value = raw.strip()
    if value in {"", "-"}:
        return []
    result: list[str] = []
    for item in value.split(","):
        candidate = item.strip()
        if not candidate:
            continue
        result.append(_normalize_participant_label(candidate))
    return sorted(set(result))


def _to_user_tz(dt: datetime, timezone: str) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(ZoneInfo(timezone))


def _format_conflicts(error: ServiceConflictError, timezone: str) -> str:
    lines = [f"Conflict detected with existing events (timezone: {timezone}):"]
    for item in error.conflicts[:10]:
        users = ", ".join(item.conflicting_participants) or "(creator overlap)"
        start = _to_user_tz(item.start_at, timezone)
        end = _to_user_tz(item.end_at, timezone)
        lines.append(
            f"- #{item.event_id} {item.title} ({start:%Y-%m-%d %H:%M} - "
            f"{end:%Y-%m-%d %H:%M}), participants: {users}"
        )
    return "\n".join(lines)


async def _get_user_timezone(user_id: int) -> str:
    async with aiohttp.ClientSession() as session:
        result = await _service_client().get_user_timezone(session, user_id)
    return result.timezone


async def start_handler(message: Message) -> None:
    _register_user_aliases(message)
    await message.answer(
        "Send plain text to store diary entry.\nUse /help to manage events."
    )


async def help_handler(message: Message) -> None:
    _register_user_aliases(message)
    await message.answer(HELP_TEXT)


async def timezone_handler(message: Message) -> None:
    if message.from_user is None:
        return
    _register_user_aliases(message)
    try:
        timezone = await _get_user_timezone(message.from_user.id)
        await message.answer(f"Your timezone: {timezone}")
    except Exception as exc:
        logger.exception("Failed to get timezone")
        await message.answer(f"Failed to get timezone: {exc}")


async def set_timezone_handler(message: Message) -> None:
    if message.from_user is None or message.text is None:
        return
    _register_user_aliases(message)
    raw = message.text.replace("/set_timezone", "", 1).strip()
    if not raw:
        await message.answer("Usage: /set_timezone Europe/Kyiv")
        return

    try:
        ZoneInfo(raw)
    except ZoneInfoNotFoundError:
        await message.answer(
            "Invalid timezone. Use IANA name, for example: Europe/Kyiv"
        )
        return

    try:
        async with aiohttp.ClientSession() as session:
            result = await _service_client().set_user_timezone(
                session, message.from_user.id, raw
            )
        await message.answer(f"Timezone updated: {result.timezone}")
    except Exception as exc:
        logger.exception("Failed to set timezone")
        await message.answer(f"Failed to set timezone: {exc}")


async def create_event_handler(message: Message) -> None:
    if message.text is None or message.from_user is None:
        return
    _register_user_aliases(message)
    raw = message.text.replace("/create_event", "", 1).strip()
    try:
        timezone = await _get_user_timezone(message.from_user.id)
    except Exception as exc:
        logger.exception("Failed to get timezone")
        await message.answer(f"Failed to get timezone: {exc}")
        return

    try:
        title, start_raw, end_raw, participants_raw = [
            part.strip() for part in raw.split("|", maxsplit=3)
        ]
        payload = EventCreate(
            creator_tg_user_id=message.from_user.id,
            title=title,
            start_at=_parse_local_datetime(start_raw, timezone),
            end_at=_parse_local_datetime(end_raw, timezone),
            participants=_parse_participants(participants_raw),
        )
    except Exception:
        await message.answer("Invalid format.\n" + HELP_TEXT)
        return

    try:
        async with aiohttp.ClientSession() as session:
            created = await _service_client().create_event(session, payload)
        created_by = (
            f"@{message.from_user.username}"
            if message.from_user.username
            else message.from_user.full_name
        )
        recipients = {created.creator_tg_user_id}
        for label in created.participants:
            user_id = KNOWN_USERS.get(_normalize_participant_label(label))
            if user_id is not None:
                recipients.add(user_id)

        for user_id in recipients:
            try:
                user_tz = await _get_user_timezone(user_id)
                start_local = _to_user_tz(created.start_at, user_tz)
                end_local = _to_user_tz(created.end_at, user_tz)
                notification_text = (
                    "New event created.\n"
                    f"Who: {created_by} (id={message.from_user.id})\n"
                    f"What: {created.title}\n"
                    f"When: {start_local:%Y-%m-%d %H:%M} - {end_local:%Y-%m-%d %H:%M} ({user_tz})\n"
                    f"Event ID: #{created.id}"
                )
                await message.bot.send_message(user_id, notification_text)
            except Exception:
                logger.warning(
                    "Cannot notify user_id=%s about event_id=%s", user_id, created.id
                )
        await message.answer(f"Event #{created.id} created successfully.")
    except ServiceConflictError as conflict:
        await message.answer(_format_conflicts(conflict, timezone))
    except Exception as exc:
        logger.exception("Failed to create event")
        await message.answer(f"Failed to create event: {exc}")


async def update_event_handler(message: Message) -> None:
    if message.text is None or message.from_user is None:
        return
    _register_user_aliases(message)
    raw = message.text.replace("/update_event", "", 1).strip()
    try:
        timezone = await _get_user_timezone(message.from_user.id)
    except Exception as exc:
        logger.exception("Failed to get timezone")
        await message.answer(f"Failed to get timezone: {exc}")
        return

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
            start_at=_parse_local_datetime(start_raw, timezone),
            end_at=_parse_local_datetime(end_raw, timezone),
            participants=_parse_participants(participants_raw),
        )
    except Exception:
        await message.answer("Invalid format.\n" + HELP_TEXT)
        return

    try:
        async with aiohttp.ClientSession() as session:
            updated = await _service_client().update_event(session, event_id, payload)
        start_local = _to_user_tz(updated.start_at, timezone)
        end_local = _to_user_tz(updated.end_at, timezone)
        await message.answer(
            f"Event updated: #{updated.id} {updated.title} "
            f"{start_local:%Y-%m-%d %H:%M} - {end_local:%Y-%m-%d %H:%M} ({timezone})"
        )
    except ServiceConflictError as conflict:
        await message.answer(_format_conflicts(conflict, timezone))
    except Exception as exc:
        logger.exception("Failed to update event")
        await message.answer(f"Failed to update event: {exc}")


async def delete_event_handler(message: Message) -> None:
    if message.text is None or message.from_user is None:
        return
    _register_user_aliases(message)
    raw = message.text.replace("/delete_event", "", 1).strip()
    if not raw.isdigit():
        await message.answer("Usage: /delete_event <id>")
        return
    event_id = int(raw)

    try:
        async with aiohttp.ClientSession() as session:
            await _service_client().delete_event(
                session, event_id, EventDelete(actor_tg_user_id=message.from_user.id)
            )
        await message.answer(f"Event #{event_id} deleted.")
    except Exception as exc:
        logger.exception("Failed to delete event")
        await message.answer(f"Failed to delete event: {exc}")


async def list_events_handler(message: Message) -> None:
    if message.from_user is None:
        return
    _register_user_aliases(message)
    try:
        timezone = await _get_user_timezone(message.from_user.id)
        participant_labels: list[str] = []
        if message.from_user.username:
            participant_labels.append(
                _normalize_participant_label(message.from_user.username)
            )
        full_name = message.from_user.full_name.strip()
        if full_name:
            participant_labels.append(_normalize_participant_label(full_name))
        async with aiohttp.ClientSession() as session:
            events = await _service_client().list_events(
                session, message.from_user.id, participant_labels
            )
    except Exception as exc:
        logger.exception("Failed to list events")
        await message.answer(f"Failed to list events: {exc}")
        return

    if not events:
        await message.answer("No events found.")
        return

    lines = [f"Your events (timezone: {timezone}):"]
    for item in events[:20]:
        start_local = _to_user_tz(item.start_at, timezone)
        end_local = _to_user_tz(item.end_at, timezone)
        participants = ",".join(item.participants) or "-"
        lines.append(
            f"#{item.id} {item.title}\n"
            f"{start_local:%Y-%m-%d %H:%M} - {end_local:%Y-%m-%d %H:%M} ({timezone})\n"
            f"participants: {participants}"
        )
    await message.answer("\n\n".join(lines))


async def list_events_today_handler(message: Message) -> None:
    if message.from_user is None:
        return
    _register_user_aliases(message)
    try:
        timezone = await _get_user_timezone(message.from_user.id)
        participant_labels: list[str] = []
        if message.from_user.username:
            participant_labels.append(
                _normalize_participant_label(message.from_user.username)
            )
        full_name = message.from_user.full_name.strip()
        if full_name:
            participant_labels.append(_normalize_participant_label(full_name))
        async with aiohttp.ClientSession() as session:
            events = await _service_client().list_events(
                session, message.from_user.id, participant_labels
            )
    except Exception as exc:
        logger.exception("Failed to list today's events")
        await message.answer(f"Failed to list today's events: {exc}")
        return

    now_local = datetime.now(ZoneInfo(timezone))
    today = now_local.date()
    today_events = [
        item for item in events if _to_user_tz(item.start_at, timezone).date() == today
    ]

    if not today_events:
        await message.answer(f"No events for today ({timezone}).")
        return

    lines = [f"Today's events ({timezone}):"]
    for item in today_events[:20]:
        start_local = _to_user_tz(item.start_at, timezone)
        end_local = _to_user_tz(item.end_at, timezone)
        participants = ",".join(item.participants) or "-"
        lines.append(
            f"#{item.id} {item.title}\n"
            f"{start_local:%Y-%m-%d %H:%M} - {end_local:%Y-%m-%d %H:%M} ({timezone})\n"
            f"participants: {participants}"
        )
    await message.answer("\n\n".join(lines))


async def text_handler(message: Message) -> None:
    if message.text is None or message.from_user is None:
        return
    _register_user_aliases(message)

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
                    timezone = await _get_user_timezone(item.creator_tg_user_id)
                    start_local = _to_user_tz(item.start_at, timezone)
                    await bot.send_message(
                        item.creator_tg_user_id,
                        (
                            "Reminder: in about 10 minutes your event starts.\n"
                            f"#{item.event_id} {item.title}\n"
                            f"Start: {start_local:%Y-%m-%d %H:%M} ({timezone})"
                        ),
                    )
                    await _service_client().mark_reminder_sent(session, item.event_id)
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
    dp.message.register(set_timezone_handler, Command("set_timezone"))
    dp.message.register(timezone_handler, Command("timezone"))
    dp.message.register(create_event_handler, Command("create_event"))
    dp.message.register(update_event_handler, Command("update_event"))
    dp.message.register(delete_event_handler, Command("delete_event"))
    dp.message.register(list_events_handler, Command("events"))
    dp.message.register(list_events_today_handler, Command("events_today"))
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
