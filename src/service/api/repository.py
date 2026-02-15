from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db.models import DiaryEntry, Event, EventParticipant, User, UserSetting
from .schemas import (
    ConflictItem,
    DiaryEntryCreate,
    DiaryEntryDelete,
    DiaryEntryOut,
    DiaryEntryUpdate,
    EventCreate,
    EventDelete,
    EventOut,
    EventUpdate,
    ReminderOut,
    UserOut,
    UserResolveOut,
    UserTimezoneOut,
    UserTimezoneSet,
    UserUpsert,
)


def _diary_entry_to_out(entry: DiaryEntry) -> DiaryEntryOut:
    return DiaryEntryOut(
        id=entry.id,
        tg_user_id=entry.tg_user_id,
        username=entry.username,
        chat_id=entry.chat_id,
        message_id=entry.message_id,
        text=entry.text,
        created_at=entry.created_at,
    )


async def create_diary_entry(
    session: AsyncSession, payload: DiaryEntryCreate
) -> DiaryEntry:
    entry = DiaryEntry(
        tg_user_id=payload.tg_user_id,
        username=payload.username,
        chat_id=payload.chat_id,
        message_id=payload.message_id,
        text=payload.text,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def list_diary_entries_for_user(
    session: AsyncSession, user_id: int
) -> list[DiaryEntryOut]:
    query = (
        select(DiaryEntry)
        .where(DiaryEntry.tg_user_id == user_id)
        .order_by(DiaryEntry.created_at.desc(), DiaryEntry.id.desc())
    )
    rows = (await session.execute(query)).scalars()
    return [_diary_entry_to_out(item) for item in rows]


async def update_diary_entry(
    session: AsyncSession,
    entry_id: int,
    payload: DiaryEntryUpdate,
) -> tuple[DiaryEntryOut | None, bool]:
    row = (
        await session.execute(select(DiaryEntry).where(DiaryEntry.id == entry_id))
    ).scalar_one_or_none()
    if row is None:
        return None, False
    if row.tg_user_id != payload.actor_tg_user_id:
        raise PermissionError("Only owner can update diary entry")

    row.text = payload.text
    await session.commit()
    await session.refresh(row)
    return _diary_entry_to_out(row), True


async def delete_diary_entry(
    session: AsyncSession,
    entry_id: int,
    payload: DiaryEntryDelete,
) -> bool:
    row = (
        await session.execute(select(DiaryEntry).where(DiaryEntry.id == entry_id))
    ).scalar_one_or_none()
    if row is None:
        return False
    if row.tg_user_id != payload.actor_tg_user_id:
        raise PermissionError("Only owner can delete diary entry")

    await session.delete(row)
    await session.commit()
    return True


def _normalize_participants(participants: list[int]) -> list[int]:
    cleaned: set[int] = set()
    for value in participants:
        if value < 1:
            continue
        cleaned.add(value)
    return sorted(cleaned)


def _ensure_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _event_to_out(event: Event) -> EventOut:
    return EventOut(
        id=event.id,
        creator_tg_user_id=event.creator_tg_user_id,
        title=event.title,
        start_at=event.start_at,
        end_at=event.end_at,
        participants=sorted(
            [item.participant_tg_user_id for item in event.participants]
        ),
    )


def _event_conflict_labels(event: Event, labels: set[int]) -> list[int]:
    involved = {item.participant_tg_user_id for item in event.participants}
    return sorted(involved.intersection(labels))


async def _find_conflicts(
    session: AsyncSession,
    creator_id: int,
    labels: set[int],
    start_at: datetime,
    end_at: datetime,
    *,
    exclude_event_id: int | None = None,
) -> list[Event]:
    query = (
        select(Event)
        .outerjoin(EventParticipant, EventParticipant.event_id == Event.id)
        .options(selectinload(Event.participants))
        .where(Event.start_at < end_at, Event.end_at > start_at)
        .where(
            or_(
                Event.creator_tg_user_id == creator_id,
                EventParticipant.participant_tg_user_id.in_(labels),
            )
        )
        .order_by(Event.start_at.asc())
    )
    if exclude_event_id is not None:
        query = query.where(Event.id != exclude_event_id)
    query = query.distinct()
    result = await session.execute(query)
    return list(result.scalars())


async def create_event(
    session: AsyncSession, payload: EventCreate
) -> tuple[EventOut | None, list[ConflictItem]]:
    start_at = _ensure_timezone(payload.start_at)
    end_at = _ensure_timezone(payload.end_at)
    now = datetime.now(UTC)
    if start_at < now:
        raise ValueError("start_at must be greater than or equal to current time")
    if end_at <= start_at:
        raise ValueError("end_at must be later than start_at")

    participant_labels = _normalize_participants(payload.participants)
    labels = set(participant_labels)
    conflicts = await _find_conflicts(
        session, payload.creator_tg_user_id, labels, start_at, end_at
    )
    if conflicts:
        return None, [
            ConflictItem(
                event_id=item.id,
                title=item.title,
                start_at=item.start_at,
                end_at=item.end_at,
                conflicting_participants=_event_conflict_labels(item, labels),
            )
            for item in conflicts
        ]

    event = Event(
        creator_tg_user_id=payload.creator_tg_user_id,
        title=payload.title,
        start_at=start_at,
        end_at=end_at,
        reminder_sent=False,
    )
    session.add(event)
    await session.flush()

    if participant_labels:
        session.add_all(
            [
                EventParticipant(event_id=event.id, participant_tg_user_id=label)
                for label in participant_labels
            ]
        )

    await session.commit()
    await session.refresh(event, attribute_names=["participants"])
    return _event_to_out(event), []


async def update_event(
    session: AsyncSession,
    event_id: int,
    payload: EventUpdate,
) -> tuple[EventOut | None, list[ConflictItem], bool]:
    event_query = (
        select(Event)
        .options(selectinload(Event.participants))
        .where(Event.id == event_id)
    )
    current = (await session.execute(event_query)).scalar_one_or_none()
    if current is None:
        return None, [], False
    if current.creator_tg_user_id != payload.actor_tg_user_id:
        raise PermissionError("Only creator can update event")

    start_at = _ensure_timezone(payload.start_at)
    end_at = _ensure_timezone(payload.end_at)
    now = datetime.now(UTC)
    if start_at < now:
        raise ValueError("start_at must be greater than or equal to current time")
    if end_at <= start_at:
        raise ValueError("end_at must be later than start_at")

    participant_labels = _normalize_participants(payload.participants)
    labels = set(participant_labels)
    conflicts = await _find_conflicts(
        session,
        payload.actor_tg_user_id,
        labels,
        start_at,
        end_at,
        exclude_event_id=event_id,
    )
    if conflicts:
        return (
            None,
            [
                ConflictItem(
                    event_id=item.id,
                    title=item.title,
                    start_at=item.start_at,
                    end_at=item.end_at,
                    conflicting_participants=_event_conflict_labels(item, labels),
                )
                for item in conflicts
            ],
            True,
        )

    current.title = payload.title
    current.start_at = start_at
    current.end_at = end_at
    current.reminder_sent = False

    await session.execute(
        delete(EventParticipant).where(EventParticipant.event_id == event_id)
    )
    if participant_labels:
        session.add_all(
            [
                EventParticipant(event_id=event_id, participant_tg_user_id=label)
                for label in participant_labels
            ]
        )

    await session.commit()
    refreshed = (await session.execute(event_query)).scalar_one()
    return _event_to_out(refreshed), [], True


async def delete_event(
    session: AsyncSession, event_id: int, payload: EventDelete
) -> bool:
    event = (
        await session.execute(select(Event).where(Event.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        return False
    if event.creator_tg_user_id != payload.actor_tg_user_id:
        raise PermissionError("Only creator can delete event")

    await session.delete(event)
    await session.commit()
    return True


async def list_events_for_user(session: AsyncSession, user_id: int) -> list[EventOut]:
    query = (
        select(Event)
        .outerjoin(EventParticipant, EventParticipant.event_id == Event.id)
        .options(selectinload(Event.participants))
        .where(
            or_(
                Event.creator_tg_user_id == user_id,
                EventParticipant.participant_tg_user_id == user_id,
            )
        )
        .order_by(Event.start_at.asc())
        .distinct()
    )
    result = await session.execute(query)
    return [_event_to_out(item) for item in result.scalars()]


async def claim_due_reminders(
    session: AsyncSession, now: datetime
) -> list[ReminderOut]:
    now = _ensure_timezone(now)
    deadline = now + timedelta(minutes=10)

    query = (
        select(Event)
        .where(
            and_(
                Event.reminder_sent.is_(False),
                Event.start_at > now,
                Event.start_at <= deadline,
            )
        )
        .order_by(Event.start_at.asc())
    )
    events = list((await session.execute(query)).scalars())
    if not events:
        return []

    event_ids = [item.id for item in events]
    participant_rows = await session.execute(
        select(EventParticipant).where(EventParticipant.event_id.in_(event_ids))
    )
    participants_by_event: dict[int, set[int]] = {}
    for row in participant_rows.scalars():
        participants_by_event.setdefault(row.event_id, set()).add(
            row.participant_tg_user_id
        )

    return [
        ReminderOut(
            event_id=item.id,
            recipients=sorted(
                {item.creator_tg_user_id}.union(
                    participants_by_event.get(item.id, set())
                )
            ),
            title=item.title,
            start_at=item.start_at,
        )
        for item in events
    ]


async def mark_reminder_sent(session: AsyncSession, event_id: int) -> bool:
    updated = await session.execute(
        update(Event)
        .where(Event.id == event_id, Event.reminder_sent.is_(False))
        .values(reminder_sent=True)
    )
    await session.commit()
    return (updated.rowcount or 0) > 0


def _validate_timezone(timezone: str) -> str:
    candidate = timezone.strip()
    if not candidate:
        raise ValueError("timezone cannot be empty")
    try:
        ZoneInfo(candidate)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("invalid timezone") from exc
    return candidate


async def get_user_timezone(session: AsyncSession, user_id: int) -> UserTimezoneOut:
    row = (
        await session.execute(
            select(UserSetting).where(UserSetting.tg_user_id == user_id)
        )
    ).scalar_one_or_none()
    if row is None:
        return UserTimezoneOut(tg_user_id=user_id, timezone="UTC")
    return UserTimezoneOut(tg_user_id=user_id, timezone=row.timezone)


async def set_user_timezone(
    session: AsyncSession, user_id: int, payload: UserTimezoneSet
) -> UserTimezoneOut:
    timezone = _validate_timezone(payload.timezone)
    current = (
        await session.execute(
            select(UserSetting).where(UserSetting.tg_user_id == user_id)
        )
    ).scalar_one_or_none()
    if current is None:
        current = UserSetting(tg_user_id=user_id, timezone=timezone)
        session.add(current)
    else:
        current.timezone = timezone
    await session.commit()
    return UserTimezoneOut(tg_user_id=user_id, timezone=timezone)


def _normalize_user_tag(tag: str | None) -> str | None:
    if tag is None:
        return None
    candidate = tag.strip()
    if not candidate:
        return None
    if candidate.startswith("@"):
        candidate = candidate[1:]
    return candidate.casefold()


async def upsert_user(
    session: AsyncSession, user_id: int, payload: UserUpsert
) -> UserOut:
    tag = _normalize_user_tag(payload.tag)
    name = payload.name.strip()
    if not name:
        raise ValueError("name cannot be empty")

    if tag is not None:
        await session.execute(
            update(User)
            .where(User.tag == tag, User.tg_user_id != user_id)
            .values(tag=None)
        )

    row = (
        await session.execute(select(User).where(User.tg_user_id == user_id))
    ).scalar_one_or_none()
    if row is None:
        row = User(tg_user_id=user_id, name=name, tag=tag)
        session.add(row)
    else:
        row.name = name
        row.tag = tag
    await session.commit()
    return UserOut(tg_user_id=row.tg_user_id, name=row.name, tag=row.tag)


async def resolve_users_by_labels(
    session: AsyncSession, labels: list[str]
) -> UserResolveOut:
    normalized_labels: list[str] = []
    for label in labels:
        candidate = label.strip()
        if not candidate:
            continue
        if candidate.startswith("@"):
            candidate = candidate[1:]
        normalized_labels.append(candidate.casefold())

    if not normalized_labels:
        return UserResolveOut(resolved={}, unresolved=[])

    unique_labels = sorted(set(normalized_labels))
    users = (
        await session.execute(
            select(User).where(
                or_(
                    User.tag.in_(unique_labels),
                    func.lower(User.name).in_(unique_labels),
                )
            )
        )
    ).scalars()
    resolved: dict[str, int] = {}
    for user in users:
        if user.tag and user.tag in unique_labels:
            resolved[user.tag] = user.tg_user_id
        user_name_key = user.name.casefold()
        if user_name_key in unique_labels:
            resolved[user_name_key] = user.tg_user_id

    unresolved = [label for label in unique_labels if label not in resolved]
    return UserResolveOut(resolved=resolved, unresolved=unresolved)
