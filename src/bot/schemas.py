from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class DiaryEntryCreate:
    tg_user_id: int
    username: str | None
    chat_id: int
    message_id: int
    text: str


@dataclass(slots=True)
class EventCreate:
    creator_tg_user_id: int
    title: str
    start_at: datetime
    end_at: datetime
    participant_tg_user_ids: list[int]


@dataclass(slots=True)
class EventUpdate:
    actor_tg_user_id: int
    title: str
    start_at: datetime
    end_at: datetime
    participant_tg_user_ids: list[int]


@dataclass(slots=True)
class EventDelete:
    actor_tg_user_id: int


@dataclass(slots=True)
class EventOut:
    id: int
    creator_tg_user_id: int
    title: str
    start_at: datetime
    end_at: datetime
    participant_tg_user_ids: list[int]


@dataclass(slots=True)
class ConflictItem:
    event_id: int
    title: str
    start_at: datetime
    end_at: datetime
    conflicting_user_ids: list[int]


@dataclass(slots=True)
class ReminderOut:
    event_id: int
    creator_tg_user_id: int
    title: str
    start_at: datetime
