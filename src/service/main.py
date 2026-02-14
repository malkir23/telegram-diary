import asyncio

from aiohttp import web

from .api.handlers import setup_routes
from .config import settings
from .db.lifecycle import on_cleanup, on_startup


def create_app() -> web.Application:
    app = web.Application()
    setup_routes(app)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


async def run() -> None:
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=settings.service_host, port=settings.service_port)
    await site.start()

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(run())
