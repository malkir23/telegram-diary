import asyncio
import logging

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message

from .client import DiaryServiceClient
from .config import settings
from .schemas import DiaryEntryCreate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _service_client() -> DiaryServiceClient:
    return DiaryServiceClient()


async def start_handler(message: Message) -> None:
    await message.answer("Надсилай текст, і я збережу його у щоденник.")


async def text_handler(message: Message) -> None:
    if message.text is None or message.from_user is None:
        return

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
        await message.answer(f"Не вдалося зберегти запис: {exc}")
        return

    await message.answer("Запис збережено.")


async def run() -> None:
    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher()

    dp.message.register(start_handler, CommandStart())
    dp.message.register(text_handler, F.text)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(run())
