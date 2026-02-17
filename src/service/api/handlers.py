from __future__ import annotations

from datetime import UTC, datetime

from aiohttp import web
from pydantic import ValidationError

from ..db.lifecycle import session_scope
from .repository import (
    claim_due_reminders,
    create_budget_contribution,
    create_diary_entry,
    create_event,
    create_expense,
    delete_diary_entry,
    delete_event,
    get_budget_daily_limit,
    get_budget_summary,
    get_daily_limit_status,
    get_user_timezone,
    list_diary_entries_for_user,
    list_events_for_user,
    list_expenses,
    mark_reminder_sent,
    resolve_users_by_labels,
    set_budget_daily_limit,
    set_user_timezone,
    update_diary_entry,
    update_event,
    upsert_user,
)
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
    UserTimezoneSet,
    UserUpsert,
)


async def _parse_json(request: web.Request) -> dict:
    data = await request.json()
    if not isinstance(data, dict):
        raise ValueError("JSON object expected")
    return data


def _conflicts_response(conflicts: list[dict]) -> web.Response:
    return web.json_response(
        {"detail": "Conflict detected", "conflicts": conflicts}, status=409
    )


async def health(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def root(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def create_entry(request: web.Request) -> web.Response:
    try:
        payload = DiaryEntryCreate.model_validate(await _parse_json(request))
    except (ValueError, ValidationError) as exc:
        return web.json_response({"detail": str(exc)}, status=422)

    async with session_scope() as session:
        entry = await create_diary_entry(session, payload)

    return web.json_response(
        {
            "id": entry.id,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        },
        status=201,
    )


async def list_entries_handler(request: web.Request) -> web.Response:
    user_id_raw = request.query.get("user_id", "")
    if not user_id_raw.isdigit():
        return web.json_response(
            {"detail": "user_id is required and must be integer"}, status=400
        )
    user_id = int(user_id_raw)

    async with session_scope() as session:
        entries = await list_diary_entries_for_user(session, user_id)
    return web.json_response(
        [item.model_dump(mode="json") for item in entries], status=200
    )


async def update_entry_handler(request: web.Request) -> web.Response:
    entry_id_raw = request.match_info.get("entry_id", "0")
    if not entry_id_raw.isdigit():
        return web.json_response({"detail": "Invalid entry_id"}, status=400)
    entry_id = int(entry_id_raw)

    try:
        payload = DiaryEntryUpdate.model_validate(await _parse_json(request))
    except (ValueError, ValidationError) as exc:
        return web.json_response({"detail": str(exc)}, status=422)

    async with session_scope() as session:
        try:
            updated, exists = await update_diary_entry(session, entry_id, payload)
        except PermissionError as exc:
            return web.json_response({"detail": str(exc)}, status=403)

    if not exists:
        return web.json_response({"detail": "Diary entry not found"}, status=404)
    return web.json_response(updated.model_dump(mode="json"), status=200)


async def delete_entry_handler(request: web.Request) -> web.Response:
    entry_id_raw = request.match_info.get("entry_id", "0")
    if not entry_id_raw.isdigit():
        return web.json_response({"detail": "Invalid entry_id"}, status=400)
    entry_id = int(entry_id_raw)

    try:
        payload = DiaryEntryDelete.model_validate(await _parse_json(request))
    except (ValueError, ValidationError) as exc:
        return web.json_response({"detail": str(exc)}, status=422)

    async with session_scope() as session:
        try:
            deleted = await delete_diary_entry(session, entry_id, payload)
        except PermissionError as exc:
            return web.json_response({"detail": str(exc)}, status=403)

    if not deleted:
        return web.json_response({"detail": "Diary entry not found"}, status=404)
    return web.json_response({"status": "deleted"}, status=200)


async def create_event_handler(request: web.Request) -> web.Response:
    try:
        payload = EventCreate.model_validate(await _parse_json(request))
    except (ValueError, ValidationError) as exc:
        return web.json_response({"detail": str(exc)}, status=422)

    async with session_scope() as session:
        try:
            created, conflicts = await create_event(session, payload)
        except ValueError as exc:
            return web.json_response({"detail": str(exc)}, status=422)

    if conflicts:
        return _conflicts_response([item.model_dump(mode="json") for item in conflicts])
    return web.json_response(created.model_dump(mode="json"), status=201)


async def update_event_handler(request: web.Request) -> web.Response:
    event_id_raw = request.match_info.get("event_id", "0")
    if not event_id_raw.isdigit():
        return web.json_response({"detail": "Invalid event_id"}, status=400)
    event_id = int(event_id_raw)

    try:
        payload = EventUpdate.model_validate(await _parse_json(request))
    except (ValueError, ValidationError) as exc:
        return web.json_response({"detail": str(exc)}, status=422)

    async with session_scope() as session:
        try:
            updated, conflicts, exists = await update_event(session, event_id, payload)
        except PermissionError as exc:
            return web.json_response({"detail": str(exc)}, status=403)
        except ValueError as exc:
            return web.json_response({"detail": str(exc)}, status=422)

    if not exists:
        return web.json_response({"detail": "Event not found"}, status=404)
    if conflicts:
        return _conflicts_response([item.model_dump(mode="json") for item in conflicts])
    return web.json_response(updated.model_dump(mode="json"), status=200)


async def delete_event_handler(request: web.Request) -> web.Response:
    event_id_raw = request.match_info.get("event_id", "0")
    if not event_id_raw.isdigit():
        return web.json_response({"detail": "Invalid event_id"}, status=400)
    event_id = int(event_id_raw)

    try:
        payload = EventDelete.model_validate(await _parse_json(request))
    except (ValueError, ValidationError) as exc:
        return web.json_response({"detail": str(exc)}, status=422)

    async with session_scope() as session:
        try:
            deleted = await delete_event(session, event_id, payload)
        except PermissionError as exc:
            return web.json_response({"detail": str(exc)}, status=403)

    if not deleted:
        return web.json_response({"detail": "Event not found"}, status=404)
    return web.json_response({"status": "deleted"}, status=200)


async def list_events_handler(request: web.Request) -> web.Response:
    user_id_raw = request.query.get("user_id", "")
    if not user_id_raw.isdigit():
        return web.json_response(
            {"detail": "user_id is required and must be integer"}, status=400
        )
    user_id = int(user_id_raw)

    async with session_scope() as session:
        events = await list_events_for_user(session, user_id)
    return web.json_response(
        [item.model_dump(mode="json") for item in events], status=200
    )


async def claim_reminders_handler(_: web.Request) -> web.Response:
    now = datetime.now(UTC)
    async with session_scope() as session:
        reminders = await claim_due_reminders(session, now)
    return web.json_response(
        [item.model_dump(mode="json") for item in reminders], status=200
    )


async def mark_reminder_sent_handler(request: web.Request) -> web.Response:
    event_id_raw = request.match_info.get("event_id", "0")
    if not event_id_raw.isdigit():
        return web.json_response({"detail": "Invalid event_id"}, status=400)
    event_id = int(event_id_raw)

    async with session_scope() as session:
        updated = await mark_reminder_sent(session, event_id)
    return web.json_response({"status": "ok", "updated": updated}, status=200)


async def create_budget_contribution_handler(request: web.Request) -> web.Response:
    try:
        payload = BudgetContributionCreate.model_validate(await _parse_json(request))
    except (ValueError, ValidationError) as exc:
        return web.json_response({"detail": str(exc)}, status=422)

    async with session_scope() as session:
        try:
            created = await create_budget_contribution(session, payload)
        except ValueError as exc:
            return web.json_response({"detail": str(exc)}, status=422)
    return web.json_response(created.model_dump(mode="json"), status=201)


async def create_expense_handler(request: web.Request) -> web.Response:
    try:
        payload = ExpenseCreate.model_validate(await _parse_json(request))
    except (ValueError, ValidationError) as exc:
        return web.json_response({"detail": str(exc)}, status=422)

    async with session_scope() as session:
        try:
            created = await create_expense(session, payload)
        except ValueError as exc:
            return web.json_response({"detail": str(exc)}, status=422)
    return web.json_response(created.model_dump(mode="json"), status=201)


async def budget_summary_handler(request: web.Request) -> web.Response:
    user_id_raw = request.query.get("user_id", "")
    if not user_id_raw.isdigit():
        return web.json_response(
            {"detail": "user_id is required and must be integer"}, status=400
        )
    user_id = int(user_id_raw)

    async with session_scope() as session:
        summary = await get_budget_summary(session, user_id=user_id)
    return web.json_response(summary.model_dump(mode="json"), status=200)


async def list_expenses_handler(request: web.Request) -> web.Response:
    user_id_raw = request.query.get("user_id")
    if user_id_raw is not None and not user_id_raw.isdigit():
        return web.json_response(
            {"detail": "user_id must be integer when provided"}, status=400
        )

    limit_raw = request.query.get("limit", "20")
    if not limit_raw.isdigit():
        return web.json_response({"detail": "limit must be integer"}, status=400)
    limit = int(limit_raw)

    async with session_scope() as session:
        expenses = await list_expenses(
            session,
            user_id=int(user_id_raw) if user_id_raw is not None else None,
            limit=limit,
        )
    return web.json_response(
        [item.model_dump(mode="json") for item in expenses], status=200
    )


async def get_budget_daily_limit_handler(_: web.Request) -> web.Response:
    async with session_scope() as session:
        result = await get_budget_daily_limit(session)
    return web.json_response(result.model_dump(mode="json"), status=200)


async def set_budget_daily_limit_handler(request: web.Request) -> web.Response:
    try:
        payload = BudgetDailyLimitSet.model_validate(await _parse_json(request))
    except (ValueError, ValidationError) as exc:
        return web.json_response({"detail": str(exc)}, status=422)

    async with session_scope() as session:
        try:
            result = await set_budget_daily_limit(session, payload)
        except ValueError as exc:
            return web.json_response({"detail": str(exc)}, status=422)
    return web.json_response(result.model_dump(mode="json"), status=200)


async def budget_daily_status_handler(request: web.Request) -> web.Response:
    user_id_raw = request.query.get("user_id", "")
    if not user_id_raw.isdigit():
        return web.json_response(
            {"detail": "user_id is required and must be integer"}, status=400
        )
    user_id = int(user_id_raw)

    async with session_scope() as session:
        status = await get_daily_limit_status(session, user_id=user_id)
    return web.json_response(status.model_dump(mode="json"), status=200)


async def get_user_timezone_handler(request: web.Request) -> web.Response:
    user_id_raw = request.match_info.get("user_id", "0")
    if not user_id_raw.isdigit():
        return web.json_response({"detail": "Invalid user_id"}, status=400)
    user_id = int(user_id_raw)

    async with session_scope() as session:
        result = await get_user_timezone(session, user_id)
    return web.json_response(result.model_dump(mode="json"), status=200)


async def set_user_timezone_handler(request: web.Request) -> web.Response:
    user_id_raw = request.match_info.get("user_id", "0")
    if not user_id_raw.isdigit():
        return web.json_response({"detail": "Invalid user_id"}, status=400)
    user_id = int(user_id_raw)

    try:
        payload = UserTimezoneSet.model_validate(await _parse_json(request))
    except (ValueError, ValidationError) as exc:
        return web.json_response({"detail": str(exc)}, status=422)

    async with session_scope() as session:
        try:
            result = await set_user_timezone(session, user_id, payload)
        except ValueError as exc:
            return web.json_response({"detail": str(exc)}, status=422)
    return web.json_response(result.model_dump(mode="json"), status=200)


async def upsert_user_handler(request: web.Request) -> web.Response:
    user_id_raw = request.match_info.get("user_id", "0")
    if not user_id_raw.isdigit():
        return web.json_response({"detail": "Invalid user_id"}, status=400)
    user_id = int(user_id_raw)

    try:
        payload = UserUpsert.model_validate(await _parse_json(request))
    except (ValueError, ValidationError) as exc:
        return web.json_response({"detail": str(exc)}, status=422)

    async with session_scope() as session:
        try:
            result = await upsert_user(session, user_id, payload)
        except ValueError as exc:
            return web.json_response({"detail": str(exc)}, status=422)
    return web.json_response(result.model_dump(mode="json"), status=200)


async def resolve_users_handler(request: web.Request) -> web.Response:
    labels_raw = request.query.get("labels", "")
    labels = [item.strip() for item in labels_raw.split(",") if item.strip()]
    async with session_scope() as session:
        result = await resolve_users_by_labels(session, labels)
    return web.json_response(result.model_dump(mode="json"), status=200)


def setup_routes(app: web.Application) -> None:
    app.router.add_get("/", root)
    app.router.add_get("/health", health)
    app.router.add_post("/diary-entries", create_entry)
    app.router.add_get("/diary-entries", list_entries_handler)
    app.router.add_put("/diary-entries/{entry_id}", update_entry_handler)
    app.router.add_delete("/diary-entries/{entry_id}", delete_entry_handler)
    app.router.add_post("/events", create_event_handler)
    app.router.add_put("/events/{event_id}", update_event_handler)
    app.router.add_delete("/events/{event_id}", delete_event_handler)
    app.router.add_get("/events", list_events_handler)
    app.router.add_post("/events/reminders/claim", claim_reminders_handler)
    app.router.add_post("/events/{event_id}/reminder-sent", mark_reminder_sent_handler)
    app.router.add_post("/budget/contributions", create_budget_contribution_handler)
    app.router.add_post("/budget/expenses", create_expense_handler)
    app.router.add_get("/budget/summary", budget_summary_handler)
    app.router.add_get("/budget/expenses", list_expenses_handler)
    app.router.add_get("/budget/daily-limit", get_budget_daily_limit_handler)
    app.router.add_put("/budget/daily-limit", set_budget_daily_limit_handler)
    app.router.add_get("/budget/daily-status", budget_daily_status_handler)
    app.router.add_get("/users/{user_id}/timezone", get_user_timezone_handler)
    app.router.add_put("/users/{user_id}/timezone", set_user_timezone_handler)
    app.router.add_put("/users/{user_id}", upsert_user_handler)
    app.router.add_get("/users/resolve", resolve_users_handler)
