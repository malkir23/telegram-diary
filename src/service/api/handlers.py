import json

from aiohttp import web
from pydantic import ValidationError

from ..config import settings
from ..db.lifecycle import session_scope
from .repository import create_diary_entry
from .schemas import DiaryEntryCreate


async def health(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def create_entry(request: web.Request) -> web.Response:
    api_key = request.headers.get("X-API-Key")
    if api_key != settings.service_api_key:
        return web.json_response({"detail": "Unauthorized"}, status=401)

    try:
        payload = DiaryEntryCreate.model_validate(await request.json(loads=json.loads))
    except json.JSONDecodeError:
        return web.json_response({"detail": "Invalid JSON"}, status=400)
    except ValidationError as exc:
        return web.json_response({"detail": exc.errors()}, status=422)

    async with session_scope() as session:
        entry = await create_diary_entry(session, payload)

    return web.json_response(
        {
            "id": entry.id,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        },
        status=201,
    )


def setup_routes(app: web.Application) -> None:
    app.router.add_get("/health", health)
    app.router.add_post("/diary-entries", create_entry)
