from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from .client import DiaryServiceClient, ServiceConflictError
from .config import settings
from .schemas import (
    BudgetContributionCreate,
    BudgetDailyLimitSet,
    DiaryEntryCreate,
    DiaryEntryDelete,
    DiaryEntryUpdate,
    EventCreate,
    EventDelete,
    EventUpdate,
    ExpenseCreate,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HELP_TEXT = (
    "Commands:\n"
    "/diary\n"
    "/edit_diary <id> | <new text>\n"
    "/delete_diary <id>\n"
    "\n"
    "/set_timezone <IANA timezone>  (example: Europe/Kyiv)\n"
    "/timezone\n"
    "/create_event <title> | <start> | <end> | <participants>\n"
    "/update_event <id> | <title> | <start> | <end> | <participants>\n"
    "/delete_event <id>\n"
    "/events\n\n"
    "/events_today\n\n"
    "/add_income <amount> | <comment>\n"
    "/add_expense <amount> | <what> | <when>\n"
    "/set_daily_limit <amount>   (0 to disable)\n"
    "/daily_limit\n"
    "/budget\n"
    "/expenses [limit]\n\n"
    "Time format: YYYY-MM-DD HH:MM (in your timezone)\n"
    "Participants: comma-separated tags/names or '-'"
)


def _service_client() -> DiaryServiceClient:
    return DiaryServiceClient(base_url=settings.diary_service_url)


def _normalize_participant_label(value: str) -> str:
    candidate = value.strip()
    if candidate.startswith("@"):
        candidate = candidate[1:]
    return candidate.casefold()


async def _register_user_aliases(message: Message) -> None:
    if message.from_user is None:
        return
    tag = (
        _normalize_participant_label(message.from_user.username)
        if message.from_user.username
        else None
    )
    try:
        async with aiohttp.ClientSession() as session:
            await _service_client().upsert_user(
                session,
                message.from_user.id,
                name=message.from_user.full_name.strip() or str(message.from_user.id),
                tag=tag,
            )
    except Exception:
        logger.warning(
            "Failed to sync user profile for user_id=%s", message.from_user.id
        )


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


def _parse_amount(raw: str) -> int:
    value = raw.strip().replace(" ", "")
    if not value.isdigit():
        raise ValueError("amount must be positive integer")
    amount = int(value)
    if amount <= 0:
        raise ValueError("amount must be positive integer")
    return amount


def _display_user(name: str | None, tg_user_id: int) -> str:
    return f"{name} (id={tg_user_id})" if name else f"id={tg_user_id}"


def _to_user_tz(dt: datetime, timezone: str) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(ZoneInfo(timezone))


def _format_conflicts(error: ServiceConflictError, timezone: str) -> str:
    lines = [f"Conflict detected with existing events (timezone: {timezone}):"]
    for item in error.conflicts[:10]:
        users = ", ".join(
            str(participant_id) for participant_id in item.conflicting_participants
        )
        users = users or "(creator overlap)"
        start = _to_user_tz(item.start_at, timezone)
        end = _to_user_tz(item.end_at, timezone)
        lines.append(
            f"- #{item.event_id} {item.title} ({start:%Y-%m-%d %H:%M} - {end:%Y-%m-%d %H:%M}), "
            f"participants tg ids: {users}"
        )
    return "\n".join(lines)


async def _get_user_timezone(user_id: int) -> str:
    async with aiohttp.ClientSession() as session:
        result = await _service_client().get_user_timezone(session, user_id)
    return result.timezone


async def start_handler(message: Message) -> None:
    await _register_user_aliases(message)
    await message.answer(
        "Send plain text to store diary entry.\nUse /help to manage events and budget."
    )


async def help_handler(message: Message) -> None:
    await _register_user_aliases(message)
    await message.answer(HELP_TEXT)


async def timezone_handler(message: Message) -> None:
    if message.from_user is None:
        return
    await _register_user_aliases(message)
    try:
        timezone = await _get_user_timezone(message.from_user.id)
        await message.answer(f"Your timezone: {timezone}")
    except Exception as exc:
        logger.exception("Failed to get timezone")
        await message.answer(f"Failed to get timezone: {exc}")


async def set_timezone_handler(message: Message) -> None:
    if message.from_user is None or message.text is None:
        return
    await _register_user_aliases(message)
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
    await _register_user_aliases(message)
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
        participant_labels = _parse_participants(participants_raw)
        payload = EventCreate(
            creator_tg_user_id=message.from_user.id,
            title=title,
            start_at=_parse_local_datetime(start_raw, timezone),
            end_at=_parse_local_datetime(end_raw, timezone),
            participants=[],
        )
    except Exception:
        await message.answer("Invalid format.\n" + HELP_TEXT)
        return

    try:
        async with aiohttp.ClientSession() as session:
            resolved = await _service_client().resolve_users(
                session, participant_labels
            )
            if resolved.unresolved:
                await message.answer(
                    "Unknown participants (ask them to send any message to bot first): "
                    + ", ".join(resolved.unresolved)
                )
                return
            payload.participants = sorted(set(resolved.resolved.values()))
            created = await _service_client().create_event(session, payload)
        created_by = (
            f"@{message.from_user.username}"
            if message.from_user.username
            else message.from_user.full_name
        )
        recipients = {created.creator_tg_user_id}
        recipients.update(created.participants)

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


async def list_diary_handler(message: Message) -> None:
    if message.from_user is None:
        return
    await _register_user_aliases(message)

    try:
        async with aiohttp.ClientSession() as session:
            entries = await _service_client().list_entries(
                session, message.from_user.id
            )
    except Exception as exc:
        logger.exception("Failed to list diary entries")
        await message.answer(f"Failed to list diary entries: {exc}")
        return

    if not entries:
        await message.answer("No diary entries found.")
        return

    lines = ["Your diary entries:"]
    for item in entries[:20]:
        lines.append(f"#{item.id} [{item.created_at:%Y-%m-%d %H:%M}]\n{item.text}")
    await message.answer("\n\n".join(lines))


async def edit_diary_handler(message: Message) -> None:
    if message.text is None or message.from_user is None:
        return
    await _register_user_aliases(message)
    raw = message.text.replace("/edit_diary", "", 1).strip()
    try:
        entry_id_raw, text = [part.strip() for part in raw.split("|", maxsplit=1)]
        if not entry_id_raw.isdigit():
            raise ValueError("entry_id")
        if not text:
            raise ValueError("text")
        entry_id = int(entry_id_raw)
    except Exception:
        await message.answer("Usage: /edit_diary <id> | <new text>")
        return

    try:
        async with aiohttp.ClientSession() as session:
            updated = await _service_client().update_entry(
                session,
                entry_id,
                DiaryEntryUpdate(actor_tg_user_id=message.from_user.id, text=text),
            )
        await message.answer(
            f"Diary entry #{updated.id} updated.\n[{updated.created_at:%Y-%m-%d %H:%M}] {updated.text}"
        )
    except Exception as exc:
        logger.exception("Failed to update diary entry")
        await message.answer(f"Failed to update diary entry: {exc}")


async def delete_diary_handler(message: Message) -> None:
    if message.text is None or message.from_user is None:
        return
    await _register_user_aliases(message)
    raw = message.text.replace("/delete_diary", "", 1).strip()
    if not raw.isdigit():
        await message.answer("Usage: /delete_diary <id>")
        return
    entry_id = int(raw)

    try:
        async with aiohttp.ClientSession() as session:
            await _service_client().delete_entry(
                session,
                entry_id,
                DiaryEntryDelete(actor_tg_user_id=message.from_user.id),
            )
        await message.answer(f"Diary entry #{entry_id} deleted.")
    except Exception as exc:
        logger.exception("Failed to delete diary entry")
        await message.answer(f"Failed to delete diary entry: {exc}")


async def update_event_handler(message: Message) -> None:
    if message.text is None or message.from_user is None:
        return
    await _register_user_aliases(message)
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
        participant_labels = _parse_participants(participants_raw)
        payload = EventUpdate(
            actor_tg_user_id=message.from_user.id,
            title=title,
            start_at=_parse_local_datetime(start_raw, timezone),
            end_at=_parse_local_datetime(end_raw, timezone),
            participants=[],
        )
    except Exception:
        await message.answer("Invalid format.\n" + HELP_TEXT)
        return

    try:
        async with aiohttp.ClientSession() as session:
            resolved = await _service_client().resolve_users(
                session, participant_labels
            )
            if resolved.unresolved:
                await message.answer(
                    "Unknown participants (ask them to send any message to bot first): "
                    + ", ".join(resolved.unresolved)
                )
                return
            payload.participants = sorted(set(resolved.resolved.values()))
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
    await _register_user_aliases(message)
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
    await _register_user_aliases(message)
    try:
        timezone = await _get_user_timezone(message.from_user.id)
        async with aiohttp.ClientSession() as session:
            events = await _service_client().list_events(session, message.from_user.id)
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
        participants = ",".join(str(user_id) for user_id in item.participants) or "-"
        lines.append(
            f"#{item.id} {item.title}\n"
            f"{start_local:%Y-%m-%d %H:%M} - {end_local:%Y-%m-%d %H:%M} ({timezone})\n"
            f"participants: {participants}"
        )
    await message.answer("\n\n".join(lines))


async def list_events_today_handler(message: Message) -> None:
    if message.from_user is None:
        return
    await _register_user_aliases(message)
    try:
        timezone = await _get_user_timezone(message.from_user.id)
        async with aiohttp.ClientSession() as session:
            events = await _service_client().list_events(session, message.from_user.id)
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
        participants = ",".join(str(user_id) for user_id in item.participants) or "-"
        lines.append(
            f"#{item.id} {item.title}\n"
            f"{start_local:%Y-%m-%d %H:%M} - {end_local:%Y-%m-%d %H:%M} ({timezone})\n"
            f"participants: {participants}"
        )
    await message.answer("\n\n".join(lines))


async def add_income_handler(message: Message) -> None:
    if message.text is None or message.from_user is None:
        return
    await _register_user_aliases(message)
    raw = message.text.replace("/add_income", "", 1).strip()
    if not raw:
        await message.answer("Usage: /add_income <amount> | <comment>")
        return

    try:
        if "|" in raw:
            amount_raw, comment_raw = [
                part.strip() for part in raw.split("|", maxsplit=1)
            ]
            comment = comment_raw or None
        else:
            amount_raw = raw
            comment = None
        amount = _parse_amount(amount_raw)
    except Exception:
        await message.answer("Usage: /add_income <amount> | <comment>")
        return

    try:
        async with aiohttp.ClientSession() as session:
            created = await _service_client().add_budget_contribution(
                session,
                BudgetContributionCreate(
                    tg_user_id=message.from_user.id,
                    amount=amount,
                    comment=comment,
                ),
            )
        await message.answer(
            f"Income added: +{created.amount}. Contribution #{created.id} saved."
        )
    except Exception as exc:
        logger.exception("Failed to add income")
        await message.answer(f"Failed to add income: {exc}")


async def add_expense_handler(message: Message) -> None:
    if message.text is None or message.from_user is None:
        return
    await _register_user_aliases(message)
    raw = message.text.replace("/add_expense", "", 1).strip()
    if not raw:
        await message.answer("Usage: /add_expense <amount> | <what> | <when>")
        return

    try:
        timezone = await _get_user_timezone(message.from_user.id)
        amount_raw, category_raw, spent_at_raw = [
            part.strip() for part in raw.split("|", maxsplit=2)
        ]
        amount = _parse_amount(amount_raw)
        category = category_raw.strip()
        if not category:
            raise ValueError("empty category")
        spent_at = _parse_local_datetime(spent_at_raw, timezone)
    except Exception:
        await message.answer(
            "Usage: /add_expense <amount> | <what> | <when>\n"
            "Time format: YYYY-MM-DD HH:MM"
        )
        return

    try:
        async with aiohttp.ClientSession() as session:
            created = await _service_client().add_expense(
                session,
                ExpenseCreate(
                    tg_user_id=message.from_user.id,
                    amount=amount,
                    category=category,
                    spent_at=spent_at,
                    comment=None,
                ),
            )
        expense = created.expense
        daily = created.daily
        spent_local = _to_user_tz(expense.spent_at, timezone)
        who = _display_user(created.spender_name, expense.tg_user_id)
        lines = [
            "Expense added:",
            f"Who: {who}",
            f"What: {expense.category}",
            f"Amount: {expense.amount}",
            f"When: {spent_local:%Y-%m-%d %H:%M} ({timezone})",
            f"Expense #{expense.id}",
        ]
        if daily.daily_limit is None:
            lines.append("Daily limit: not set")
        else:
            lines.append(
                f"Daily spent: {daily.spent} / {daily.daily_limit} ({daily.date})"
            )
            lines.append(f"Daily remaining: {daily.remaining}")
            if daily.exceeded:
                lines.append(f"WARNING: daily limit exceeded by {daily.exceeded_by}.")
        await message.answer("\n".join(lines))
    except Exception as exc:
        logger.exception("Failed to add expense")
        await message.answer(f"Failed to add expense: {exc}")


async def set_daily_limit_handler(message: Message) -> None:
    if message.text is None or message.from_user is None:
        return
    await _register_user_aliases(message)
    raw = message.text.replace("/set_daily_limit", "", 1).strip()
    if not raw or not raw.isdigit():
        await message.answer("Usage: /set_daily_limit <amount> (0 to disable)")
        return
    daily_limit = int(raw)

    try:
        async with aiohttp.ClientSession() as session:
            result = await _service_client().set_daily_limit(
                session,
                BudgetDailyLimitSet(
                    actor_tg_user_id=message.from_user.id,
                    daily_limit=daily_limit,
                ),
            )
        if result.daily_limit is None:
            await message.answer("Daily limit disabled.")
        else:
            await message.answer(f"Daily limit set: {result.daily_limit}")
    except Exception as exc:
        logger.exception("Failed to set daily limit")
        await message.answer(f"Failed to set daily limit: {exc}")


async def daily_limit_handler(message: Message) -> None:
    if message.from_user is None:
        return
    await _register_user_aliases(message)
    try:
        async with aiohttp.ClientSession() as session:
            setting = await _service_client().get_daily_limit(session)
            status = await _service_client().get_daily_status(
                session, user_id=message.from_user.id
            )
    except Exception as exc:
        logger.exception("Failed to get daily limit status")
        await message.answer(f"Failed to get daily limit status: {exc}")
        return

    if setting.daily_limit is None:
        await message.answer(
            f"Daily limit is not set.\n"
            f"Spent today ({status.date}, {status.timezone}): {status.spent}"
        )
        return

    lines = [
        f"Daily limit ({status.date}, {status.timezone}): {setting.daily_limit}",
        f"Spent today: {status.spent}",
        f"Remaining today: {status.remaining}",
    ]
    if status.exceeded:
        lines.append(f"Exceeded by: {status.exceeded_by}")
    await message.answer("\n".join(lines))


async def budget_handler(message: Message) -> None:
    if message.from_user is None:
        return
    await _register_user_aliases(message)
    try:
        timezone = await _get_user_timezone(message.from_user.id)
        async with aiohttp.ClientSession() as session:
            summary = await _service_client().get_budget_summary(
                session, user_id=message.from_user.id
            )
            expenses = await _service_client().list_expenses(session, limit=10)
    except Exception as exc:
        logger.exception("Failed to build budget report")
        await message.answer(f"Failed to build budget report: {exc}")
        return

    names_by_user: dict[int, str | None] = {}
    for item in summary.contributors:
        names_by_user[item.tg_user_id] = item.name
    for item in summary.spenders:
        names_by_user[item.tg_user_id] = item.name

    lines = [
        "Budget summary:",
        f"Budget (all incomes): {summary.total_income}",
        f"Spent: {summary.total_expense}",
        f"Balance: {summary.balance}",
        "",
        f"Daily status ({summary.daily.date}, {summary.daily.timezone}):",
    ]
    if summary.daily.daily_limit is None:
        lines.append(f"Spent today: {summary.daily.spent}")
        lines.append("Daily limit: not set")
    else:
        lines.append(
            f"Spent today: {summary.daily.spent} / {summary.daily.daily_limit}"
        )
        lines.append(f"Remaining today: {summary.daily.remaining}")
        if summary.daily.exceeded:
            lines.append(f"Exceeded by: {summary.daily.exceeded_by}")

    lines.extend(
        [
            "",
            "Who contributed:",
        ]
    )
    if summary.contributors:
        for item in summary.contributors[:15]:
            lines.append(
                f"- {_display_user(item.name, item.tg_user_id)}: +{item.amount}"
            )
    else:
        lines.append("- no contributions yet")

    lines.append("")
    lines.append("Who spent:")
    if summary.spenders:
        for item in summary.spenders[:15]:
            lines.append(
                f"- {_display_user(item.name, item.tg_user_id)}: -{item.amount}"
            )
    else:
        lines.append("- no expenses yet")

    lines.append("")
    lines.append("Spent on what:")
    if summary.categories:
        for item in summary.categories[:15]:
            lines.append(f"- {item.category}: {item.amount}")
    else:
        lines.append("- no expense categories yet")

    lines.append("")
    lines.append(f"Recent expenses (timezone: {timezone}):")
    if expenses:
        for item in expenses[:10]:
            spent_local = _to_user_tz(item.spent_at, timezone)
            display_name = _display_user(
                names_by_user.get(item.tg_user_id), item.tg_user_id
            )
            lines.append(
                f"- {spent_local:%Y-%m-%d %H:%M}: {display_name} spent "
                f"{item.amount} on {item.category}"
            )
    else:
        lines.append("- no expenses yet")

    await message.answer("\n".join(lines))


async def expenses_handler(message: Message) -> None:
    if message.from_user is None:
        return
    await _register_user_aliases(message)
    raw = (message.text or "").replace("/expenses", "", 1).strip()
    limit = 20
    if raw:
        if not raw.isdigit():
            await message.answer("Usage: /expenses [limit]")
            return
        limit = int(raw)

    try:
        timezone = await _get_user_timezone(message.from_user.id)
        async with aiohttp.ClientSession() as session:
            expenses = await _service_client().list_expenses(session, limit=limit)
            summary = await _service_client().get_budget_summary(
                session, user_id=message.from_user.id
            )
    except Exception as exc:
        logger.exception("Failed to list expenses")
        await message.answer(f"Failed to list expenses: {exc}")
        return

    if not expenses:
        await message.answer("No expenses found.")
        return

    names_by_user: dict[int, str | None] = {
        item.tg_user_id: item.name for item in summary.spenders
    }
    lines = [f"Latest expenses (timezone: {timezone}):"]
    for item in expenses[:limit]:
        spent_local = _to_user_tz(item.spent_at, timezone)
        lines.append(
            f"- #{item.id} {spent_local:%Y-%m-%d %H:%M} | "
            f"{_display_user(names_by_user.get(item.tg_user_id), item.tg_user_id)} | "
            f"{item.amount} | {item.category}"
        )
    await message.answer("\n".join(lines))


async def text_handler(message: Message) -> None:
    if message.text is None or message.from_user is None:
        return
    await _register_user_aliases(message)

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
                    all_delivered = True
                    for recipient_id in item.recipients:
                        try:
                            timezone = await _get_user_timezone(recipient_id)
                            start_local = _to_user_tz(item.start_at, timezone)
                            await bot.send_message(
                                recipient_id,
                                (
                                    "Reminder: in about 10 minutes your event starts.\n"
                                    f"#{item.event_id} {item.title}\n"
                                    f"Start: {start_local:%Y-%m-%d %H:%M} ({timezone})"
                                ),
                            )
                        except TelegramForbiddenError:
                            logger.warning(
                                "User blocked bot user_id=%s event_id=%s",
                                recipient_id,
                                item.event_id,
                            )
                        except Exception:
                            all_delivered = False
                            logger.exception(
                                "Failed to notify user_id=%s for event_id=%s",
                                recipient_id,
                                item.event_id,
                            )
                    if all_delivered:
                        await _service_client().mark_reminder_sent(
                            session, item.event_id
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
    dp.message.register(list_diary_handler, Command("diary"))
    dp.message.register(edit_diary_handler, Command("edit_diary"))
    dp.message.register(delete_diary_handler, Command("delete_diary"))
    dp.message.register(set_timezone_handler, Command("set_timezone"))
    dp.message.register(timezone_handler, Command("timezone"))
    dp.message.register(create_event_handler, Command("create_event"))
    dp.message.register(update_event_handler, Command("update_event"))
    dp.message.register(delete_event_handler, Command("delete_event"))
    dp.message.register(list_events_handler, Command("events"))
    dp.message.register(list_events_today_handler, Command("events_today"))
    dp.message.register(add_income_handler, Command("add_income"))
    dp.message.register(add_expense_handler, Command("add_expense"))
    dp.message.register(set_daily_limit_handler, Command("set_daily_limit"))
    dp.message.register(daily_limit_handler, Command("daily_limit"))
    dp.message.register(budget_handler, Command("budget"))
    dp.message.register(expenses_handler, Command("expenses"))
    dp.message.register(text_handler, F.text & ~F.text.startswith("/"))

    reminder_task = asyncio.create_task(reminders_loop(bot), name="reminders-loop")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        reminder_task.cancel()
        await asyncio.gather(reminder_task, return_exceptions=True)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run())
