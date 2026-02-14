import aiohttp

from .config import settings
from .schemas import DiaryEntryCreate


class DiaryServiceClient:
    def __init__(self) -> None:
        self._base_url = settings.diary_service_url.rstrip("/")
        self._headers = {"X-API-Key": settings.diary_service_api_key}

    async def save_entry(
        self, session: aiohttp.ClientSession, entry: DiaryEntryCreate
    ) -> None:
        async with session.post(
            f"{self._base_url}/diary-entries",
            json={
                "tg_user_id": entry.tg_user_id,
                "username": entry.username,
                "chat_id": entry.chat_id,
                "message_id": entry.message_id,
                "text": entry.text,
            },
            headers=self._headers,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status >= 400:
                body = await response.text()
                raise RuntimeError(f"Service error {response.status}: {body}")
