import asyncio
import logging
import sys
from collections.abc import Sequence

from src.bot.main import run as run_bot
from src.service.main import run as run_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("app.handler")


class ApplicationHandler:
    async def run(self) -> None:
        logger.info("Starting database migrations: alembic upgrade head")
        await self._run_command([sys.executable, "-m", "alembic", "upgrade", "head"])
        logger.info("Migrations completed")

        logger.info("Starting web service and Telegram bot")
        service_task = asyncio.create_task(run_service(), name="web-service")
        bot_task = asyncio.create_task(run_bot(), name="telegram-bot")
        tasks = [service_task, bot_task]

        try:
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_EXCEPTION
            )
            for task in done:
                exc = task.exception()
                if exc is not None:
                    raise exc
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info("All tasks stopped")

    async def _run_command(self, command: Sequence[str]) -> None:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if stdout:
            logger.info("alembic stdout:\n%s", stdout.decode().strip())
        if stderr:
            logger.warning("alembic stderr:\n%s", stderr.decode().strip())

        if process.returncode != 0:
            raise RuntimeError(
                f"Command failed ({process.returncode}): {' '.join(command)}"
            )


async def run() -> None:
    handler = ApplicationHandler()
    await handler.run()
