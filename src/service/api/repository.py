from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db.models import DiaryEntry, Event, EventParticipant
from .schemas import (
    ConflictItem,
    DiaryEntryCreate,
    EventCreate,
    EventDelete,
    EventOut,
    EventUpdate,
    ReminderOut,
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


def _normalize_user_ids(creator_id: int, participant_ids: list[int]) -> list[int]:
    cleaned = {user_id for user_id in participant_ids if user_id > 0}
    cleaned.discard(creator_id)
    return sorted(cleaned)


def _ensure_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _event_to_out(event: Event) -> EventOut:
    return EventOut(
        id=event.id,
        creator_tg_user_id=event.creator_tg_user_id,
        title=event.title,
        start_at=event.start_at,
        end_at=event.end_at,
        participant_tg_user_ids=sorted(
            [item.tg_user_id for item in event.participants]
        ),
    )


def _event_conflict_users(event: Event, users: set[int]) -> list[int]:
    involved = {event.creator_tg_user_id}
    involved.update(item.tg_user_id for item in event.participants)
    return sorted(involved.intersection(users))


async def _find_conflicts(
    session: AsyncSession,
    users: set[int],
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
                Event.creator_tg_user_id.in_(users),
                EventParticipant.tg_user_id.in_(users),
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
    if end_at <= start_at:
        raise ValueError("end_at must be later than start_at")

    participant_ids = _normalize_user_ids(
        payload.creator_tg_user_id, payload.participant_tg_user_ids
    )
    involved_users = {payload.creator_tg_user_id, *participant_ids}
    conflicts = await _find_conflicts(session, involved_users, start_at, end_at)
    if conflicts:
        return None, [
            ConflictItem(
                event_id=item.id,
                title=item.title,
                start_at=item.start_at,
                end_at=item.end_at,
                conflicting_user_ids=_event_conflict_users(item, involved_users),
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

    if participant_ids:
        session.add_all(
            [
                EventParticipant(event_id=event.id, tg_user_id=user_id)
                for user_id in participant_ids
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
    if end_at <= start_at:
        raise ValueError("end_at must be later than start_at")

    participant_ids = _normalize_user_ids(
        payload.actor_tg_user_id, payload.participant_tg_user_ids
    )
    involved_users = {payload.actor_tg_user_id, *participant_ids}
    conflicts = await _find_conflicts(
        session,
        involved_users,
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
                    conflicting_user_ids=_event_conflict_users(item, involved_users),
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
    if participant_ids:
        session.add_all(
            [
                EventParticipant(event_id=event_id, tg_user_id=user_id)
                for user_id in participant_ids
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
                EventParticipant.tg_user_id == user_id,
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
    deadline = now + timedelta(hours=1)

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
