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


class EventCreate(BaseModel):
    creator_tg_user_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=255)
    start_at: datetime
    end_at: datetime
    participant_tg_user_ids: list[int] = Field(default_factory=list)


class EventUpdate(BaseModel):
    actor_tg_user_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=255)
    start_at: datetime
    end_at: datetime
    participant_tg_user_ids: list[int] = Field(default_factory=list)


class EventDelete(BaseModel):
    actor_tg_user_id: int = Field(ge=1)


class EventOut(BaseModel):
    id: int
    creator_tg_user_id: int
    title: str
    start_at: datetime
    end_at: datetime
    participant_tg_user_ids: list[int]


class ConflictItem(BaseModel):
    event_id: int
    title: str
    start_at: datetime
    end_at: datetime
    conflicting_user_ids: list[int]


class ReminderOut(BaseModel):
    event_id: int
    creator_tg_user_id: int
    title: str
    start_at: datetime
