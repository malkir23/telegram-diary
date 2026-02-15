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
    tg_user_id: int
    username: str | None
    chat_id: int
    message_id: int
    text: str
    created_at: datetime


class DiaryEntryUpdate(BaseModel):
    actor_tg_user_id: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=4096)


class DiaryEntryDelete(BaseModel):
    actor_tg_user_id: int = Field(ge=1)


class EventCreate(BaseModel):
    creator_tg_user_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=255)
    start_at: datetime
    end_at: datetime
    participants: list[int] = Field(default_factory=list)


class EventUpdate(BaseModel):
    actor_tg_user_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=255)
    start_at: datetime
    end_at: datetime
    participants: list[int] = Field(default_factory=list)


class EventDelete(BaseModel):
    actor_tg_user_id: int = Field(ge=1)


class EventOut(BaseModel):
    id: int
    creator_tg_user_id: int
    title: str
    start_at: datetime
    end_at: datetime
    participants: list[int]


class ConflictItem(BaseModel):
    event_id: int
    title: str
    start_at: datetime
    end_at: datetime
    conflicting_participants: list[int]


class ReminderOut(BaseModel):
    event_id: int
    recipients: list[int]
    title: str
    start_at: datetime


class UserUpsert(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    tag: str | None = Field(default=None, max_length=255)


class UserOut(BaseModel):
    tg_user_id: int
    name: str
    tag: str | None


class UserResolveOut(BaseModel):
    resolved: dict[str, int]
    unresolved: list[str]


class UserTimezoneSet(BaseModel):
    timezone: str = Field(min_length=1, max_length=128)


class UserTimezoneOut(BaseModel):
    tg_user_id: int
    timezone: str
