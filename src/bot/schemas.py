from dataclasses import dataclass


@dataclass(slots=True)
class DiaryEntryCreate:
    tg_user_id: int
    username: str | None
    chat_id: int
    message_id: int
    text: str
