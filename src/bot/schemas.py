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
    participants: list[int]


@dataclass(slots=True)
class EventUpdate:
    actor_tg_user_id: int
    title: str
    start_at: datetime
    end_at: datetime
    participants: list[int]


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
    participants: list[int]


@dataclass(slots=True)
class ConflictItem:
    event_id: int
    title: str
    start_at: datetime
    end_at: datetime
    conflicting_participants: list[int]


@dataclass(slots=True)
class ReminderOut:
    event_id: int
    recipients: list[int]
    title: str
    start_at: datetime


@dataclass(slots=True)
class UserTimezoneOut:
    tg_user_id: int
    timezone: str


@dataclass(slots=True)
class UserOut:
    tg_user_id: int
    name: str
    tag: str | None


@dataclass(slots=True)
class UserResolveOut:
    resolved: dict[str, int]
    unresolved: list[str]
