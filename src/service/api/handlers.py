from __future__ import annotations

from datetime import UTC, datetime

from aiohttp import web
from pydantic import ValidationError

from ..db.lifecycle import session_scope
from .repository import (
    claim_due_reminders,
    create_diary_entry,
    create_event,
    delete_event,
    get_user_timezone,
    list_events_for_user,
    set_user_timezone,
    update_event,
)
from .schemas import (
    DiaryEntryCreate,
    EventCreate,
    EventDelete,
    EventUpdate,
    UserTimezoneSet,
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
    labels_raw = request.query.get("participant_labels", "")
    participant_labels = [
        item.strip() for item in labels_raw.split(",") if item.strip()
    ]

    async with session_scope() as session:
        events = await list_events_for_user(session, user_id, participant_labels)
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


def setup_routes(app: web.Application) -> None:
    app.router.add_get("/health", health)
    app.router.add_post("/diary-entries", create_entry)
    app.router.add_post("/events", create_event_handler)
    app.router.add_put("/events/{event_id}", update_event_handler)
    app.router.add_delete("/events/{event_id}", delete_event_handler)
    app.router.add_get("/events", list_events_handler)
    app.router.add_post("/events/reminders/claim", claim_reminders_handler)
    app.router.add_get("/users/{user_id}/timezone", get_user_timezone_handler)
    app.router.add_put("/users/{user_id}/timezone", set_user_timezone_handler)
