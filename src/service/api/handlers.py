from __future__ import annotations

from datetime import UTC, datetime

from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..db.lifecycle import session_scope
from .repository import (
    claim_due_reminders,
    create_diary_entry,
    create_event,
    delete_event,
    list_events_for_user,
    update_event,
)
from .schemas import DiaryEntryCreate, EventCreate, EventDelete, EventUpdate


async def _parse_json(request: Request) -> dict:
    data = await request.json()
    if not isinstance(data, dict):
        raise ValueError("JSON object expected")
    return data


def _conflicts_response(conflicts: list[dict]) -> JSONResponse:
    return JSONResponse(
        {"detail": "Conflict detected", "conflicts": conflicts}, status_code=409
    )


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


async def create_entry(request: Request) -> JSONResponse:
    try:
        payload = DiaryEntryCreate.model_validate(await _parse_json(request))
    except (ValueError, ValidationError) as exc:
        return JSONResponse({"detail": str(exc)}, status_code=422)

    async with session_scope() as session:
        entry = await create_diary_entry(session, payload)

    return JSONResponse(
        {
            "id": entry.id,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        },
        status_code=201,
    )


async def create_event_handler(request: Request) -> JSONResponse:
    try:
        payload = EventCreate.model_validate(await _parse_json(request))
    except (ValueError, ValidationError) as exc:
        return JSONResponse({"detail": str(exc)}, status_code=422)

    async with session_scope() as session:
        try:
            created, conflicts = await create_event(session, payload)
        except ValueError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=422)

    if conflicts:
        return _conflicts_response([item.model_dump(mode="json") for item in conflicts])
    return JSONResponse(created.model_dump(mode="json"), status_code=201)


async def update_event_handler(request: Request) -> JSONResponse:
    event_id_raw = request.path_params.get("event_id", "0")
    if not str(event_id_raw).isdigit():
        return JSONResponse({"detail": "Invalid event_id"}, status_code=400)
    event_id = int(event_id_raw)

    try:
        payload = EventUpdate.model_validate(await _parse_json(request))
    except (ValueError, ValidationError) as exc:
        return JSONResponse({"detail": str(exc)}, status_code=422)

    async with session_scope() as session:
        try:
            updated, conflicts, exists = await update_event(session, event_id, payload)
        except PermissionError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=403)
        except ValueError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=422)

    if not exists:
        return JSONResponse({"detail": "Event not found"}, status_code=404)
    if conflicts:
        return _conflicts_response([item.model_dump(mode="json") for item in conflicts])
    return JSONResponse(updated.model_dump(mode="json"), status_code=200)


async def delete_event_handler(request: Request) -> JSONResponse:
    event_id_raw = request.path_params.get("event_id", "0")
    if not str(event_id_raw).isdigit():
        return JSONResponse({"detail": "Invalid event_id"}, status_code=400)
    event_id = int(event_id_raw)

    try:
        payload = EventDelete.model_validate(await _parse_json(request))
    except (ValueError, ValidationError) as exc:
        return JSONResponse({"detail": str(exc)}, status_code=422)

    async with session_scope() as session:
        try:
            deleted = await delete_event(session, event_id, payload)
        except PermissionError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=403)

    if not deleted:
        return JSONResponse({"detail": "Event not found"}, status_code=404)
    return JSONResponse({"status": "deleted"}, status_code=200)


async def list_events_handler(request: Request) -> JSONResponse:
    user_id_raw = request.query_params.get("user_id", "")
    if not user_id_raw.isdigit():
        return JSONResponse(
            {"detail": "user_id is required and must be integer"}, status_code=400
        )
    user_id = int(user_id_raw)

    async with session_scope() as session:
        events = await list_events_for_user(session, user_id)
    return JSONResponse(
        [item.model_dump(mode="json") for item in events], status_code=200
    )


async def claim_reminders_handler(_: Request) -> JSONResponse:
    now = datetime.now(UTC)
    async with session_scope() as session:
        reminders = await claim_due_reminders(session, now)
    return JSONResponse(
        [item.model_dump(mode="json") for item in reminders], status_code=200
    )
