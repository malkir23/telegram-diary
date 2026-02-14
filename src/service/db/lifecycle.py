from contextlib import asynccontextmanager

from aiohttp import web
from sqlalchemy import text

from .session import SessionLocal, engine


@asynccontextmanager
async def session_scope():
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))


async def close_db() -> None:
    await engine.dispose()


async def on_startup(_: web.Application) -> None:
    await init_db()


async def on_cleanup(_: web.Application) -> None:
    await close_db()
