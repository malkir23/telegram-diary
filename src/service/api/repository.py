from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, delete, false, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db.models import DiaryEntry, Event, EventParticipant, UserSetting
from .schemas import (
    ConflictItem,
    DiaryEntryCreate,
    EventCreate,
    EventDelete,
    EventOut,
    EventUpdate,
    ReminderOut,
    UserTimezoneOut,
    UserTimezoneSet,
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


def _normalize_participants(participants: list[str]) -> list[str]:
    cleaned: set[str] = set()
    for value in participants:
        candidate = value.strip()
        if not candidate:
            continue
        if candidate.startswith("@"):
            candidate = candidate[1:]
        cleaned.add(candidate.casefold())
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
        participants=sorted([item.participant_label for item in event.participants]),
    )


def _event_conflict_labels(event: Event, labels: set[str]) -> list[str]:
    involved = {item.participant_label for item in event.participants}
    return sorted(involved.intersection(labels))


async def _find_conflicts(
    session: AsyncSession,
    creator_id: int,
    labels: set[str],
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
                EventParticipant.participant_label.in_(labels),
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
                EventParticipant(event_id=event.id, participant_label=label)
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
                EventParticipant(event_id=event_id, participant_label=label)
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


async def list_events_for_user(
    session: AsyncSession, user_id: int, participant_labels: list[str]
) -> list[EventOut]:
    labels = _normalize_participants(participant_labels)
    participant_filter = (
        EventParticipant.participant_label.in_(labels) if labels else false()
    )
    query = (
        select(Event)
        .outerjoin(EventParticipant, EventParticipant.event_id == Event.id)
        .options(selectinload(Event.participants))
        .where(
            or_(
                Event.creator_tg_user_id == user_id,
                participant_filter,
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
    await session.execute(
        update(Event).where(Event.id.in_(event_ids)).values(reminder_sent=True)
    )
    await session.commit()

    return [
        ReminderOut(
            event_id=item.id,
            creator_tg_user_id=item.creator_tg_user_id,
            title=item.title,
            start_at=item.start_at,
        )
        for item in events
    ]


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
