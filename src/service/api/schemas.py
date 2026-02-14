from datetime import datetime

from pydantic import BaseModel, Field


class DiaryEntryCreate(BaseModel):
    tg_user_id: int = Field(ge=1)
    username: str | None = None
    chat_id: int
    message_id: int
    text: str = Field(min_length=1, max_length=4096)


class DiaryEntryOut(BaseModel):
    id: int
    created_at: datetime
