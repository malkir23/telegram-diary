from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route

from .api.handlers import (
    claim_reminders_handler,
    create_entry,
    create_event_handler,
    delete_event_handler,
    health,
    list_events_handler,
    update_event_handler,
)
from .db.lifecycle import on_cleanup, on_startup

SERVICE_HOST = "0.0.0.0"
SERVICE_PORT = 8080


@asynccontextmanager
async def lifespan(_: Starlette):
    await on_startup()
    try:
        yield
    finally:
        await on_cleanup()


def create_app() -> Starlette:
    return Starlette(
        lifespan=lifespan,
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/diary-entries", create_entry, methods=["POST"]),
            Route("/events", create_event_handler, methods=["POST"]),
            Route("/events/{event_id:int}", update_event_handler, methods=["PUT"]),
            Route("/events/{event_id:int}", delete_event_handler, methods=["DELETE"]),
            Route("/events", list_events_handler, methods=["GET"]),
            Route("/events/reminders/claim", claim_reminders_handler, methods=["POST"]),
        ],
    )


app = create_app()


async def run() -> None:
    config = uvicorn.Config(app, host=SERVICE_HOST, port=SERVICE_PORT, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    uvicorn.run(
        "src.service.main:app", host=SERVICE_HOST, port=SERVICE_PORT, reload=False
    )
