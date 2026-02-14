from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import DiaryEntry
from .schemas import DiaryEntryCreate


async def create_diary_entry(
    session: AsyncSession, payload: DiaryEntryCreate
) -> DiaryEntry:
    statement = (
        insert(DiaryEntry)
        .values(
            tg_user_id=payload.tg_user_id,
            username=payload.username,
            chat_id=payload.chat_id,
            message_id=payload.message_id,
            text=payload.text,
        )
        .returning(DiaryEntry)
    )
    result = await session.execute(statement)
    await session.commit()
    return result.scalar_one()
