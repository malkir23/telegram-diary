from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db.models import (
    BudgetContribution,
    BudgetSetting,
    DiaryEntry,
    Event,
    EventParticipant,
    Expense,
    User,
    UserSetting,
)
from .schemas import (
    BudgetCategoryStats,
    BudgetContributionCreate,
    BudgetContributionOut,
    BudgetContributorStats,
    BudgetDailyLimitOut,
    BudgetDailyLimitSet,
    BudgetSpenderStats,
    BudgetSummaryOut,
    ConflictItem,
    DailyLimitStatusOut,
    DiaryEntryCreate,
    DiaryEntryDelete,
    DiaryEntryOut,
    DiaryEntryUpdate,
    EventCreate,
    EventDelete,
    EventOut,
    EventUpdate,
    ExpenseCreate,
    ExpenseCreateOut,
    ExpenseOut,
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


def _budget_contribution_to_out(
    contribution: BudgetContribution,
) -> BudgetContributionOut:
    return BudgetContributionOut(
        id=contribution.id,
        tg_user_id=contribution.tg_user_id,
        amount=contribution.amount,
        comment=contribution.comment,
        created_at=contribution.created_at,
    )


def _expense_to_out(expense: Expense) -> ExpenseOut:
    return ExpenseOut(
        id=expense.id,
        tg_user_id=expense.tg_user_id,
        amount=expense.amount,
        category=expense.category,
        spent_at=expense.spent_at,
        comment=expense.comment,
        created_at=expense.created_at,
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


BUDGET_SETTINGS_ID = 1


async def _user_exists(session: AsyncSession, user_id: int) -> bool:
    return (
        await session.execute(select(User.tg_user_id).where(User.tg_user_id == user_id))
    ).scalar_one_or_none() is not None


async def _get_user_name(session: AsyncSession, user_id: int) -> str | None:
    return (
        await session.execute(select(User.name).where(User.tg_user_id == user_id))
    ).scalar_one_or_none()


async def _get_user_timezone_name(session: AsyncSession, user_id: int) -> str:
    timezone = (
        await session.execute(
            select(UserSetting.timezone).where(UserSetting.tg_user_id == user_id)
        )
    ).scalar_one_or_none()
    if timezone is None:
        return "UTC"
    return timezone


def _day_bounds_utc(
    anchor_utc: datetime, timezone: str
) -> tuple[datetime, datetime, str]:
    anchor_utc = _ensure_timezone(anchor_utc)
    try:
        user_zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        user_zone = ZoneInfo("UTC")
        timezone = "UTC"

    local_time = anchor_utc.astimezone(user_zone)
    day_start_local = datetime(
        local_time.year,
        local_time.month,
        local_time.day,
        tzinfo=user_zone,
    )
    day_end_local = day_start_local + timedelta(days=1)
    return (
        day_start_local.astimezone(UTC),
        day_end_local.astimezone(UTC),
        day_start_local.date().isoformat(),
    )


async def get_budget_daily_limit(session: AsyncSession) -> BudgetDailyLimitOut:
    setting = (
        await session.execute(
            select(BudgetSetting).where(BudgetSetting.id == BUDGET_SETTINGS_ID)
        )
    ).scalar_one_or_none()
    if setting is None:
        return BudgetDailyLimitOut(
            daily_limit=None,
            updated_by_tg_user_id=None,
            updated_at=None,
        )
    return BudgetDailyLimitOut(
        daily_limit=setting.daily_limit,
        updated_by_tg_user_id=setting.updated_by_tg_user_id,
        updated_at=setting.updated_at,
    )


async def set_budget_daily_limit(
    session: AsyncSession, payload: BudgetDailyLimitSet
) -> BudgetDailyLimitOut:
    if not await _user_exists(session, payload.actor_tg_user_id):
        raise ValueError("user is not registered")

    setting = (
        await session.execute(
            select(BudgetSetting).where(BudgetSetting.id == BUDGET_SETTINGS_ID)
        )
    ).scalar_one_or_none()
    new_limit = payload.daily_limit if payload.daily_limit > 0 else None
    if setting is None:
        setting = BudgetSetting(
            id=BUDGET_SETTINGS_ID,
            daily_limit=new_limit,
            updated_by_tg_user_id=payload.actor_tg_user_id,
        )
        session.add(setting)
    else:
        setting.daily_limit = new_limit
        setting.updated_by_tg_user_id = payload.actor_tg_user_id
    await session.commit()
    await session.refresh(setting)
    return BudgetDailyLimitOut(
        daily_limit=setting.daily_limit,
        updated_by_tg_user_id=setting.updated_by_tg_user_id,
        updated_at=setting.updated_at,
    )


async def get_daily_limit_status(
    session: AsyncSession,
    *,
    user_id: int,
    at: datetime | None = None,
) -> DailyLimitStatusOut:
    anchor = _ensure_timezone(at or datetime.now(UTC))
    timezone = await _get_user_timezone_name(session, user_id)
    day_start_utc, day_end_utc, day_label = _day_bounds_utc(anchor, timezone)
    spent_raw = (
        await session.execute(
            select(func.coalesce(func.sum(Expense.amount), 0)).where(
                Expense.spent_at >= day_start_utc,
                Expense.spent_at < day_end_utc,
            )
        )
    ).scalar_one()
    spent = int(spent_raw or 0)

    setting = (
        await session.execute(
            select(BudgetSetting).where(BudgetSetting.id == BUDGET_SETTINGS_ID)
        )
    ).scalar_one_or_none()
    daily_limit = setting.daily_limit if setting is not None else None
    if daily_limit is None:
        return DailyLimitStatusOut(
            date=day_label,
            timezone=timezone,
            daily_limit=None,
            spent=spent,
            remaining=None,
            exceeded=False,
            exceeded_by=0,
        )

    remaining = daily_limit - spent
    exceeded_by = max(0, spent - daily_limit)
    return DailyLimitStatusOut(
        date=day_label,
        timezone=timezone,
        daily_limit=daily_limit,
        spent=spent,
        remaining=max(0, remaining),
        exceeded=spent > daily_limit,
        exceeded_by=exceeded_by,
    )


async def create_budget_contribution(
    session: AsyncSession, payload: BudgetContributionCreate
) -> BudgetContributionOut:
    if not await _user_exists(session, payload.tg_user_id):
        raise ValueError("user is not registered")

    comment = payload.comment.strip() if payload.comment else None
    contribution = BudgetContribution(
        tg_user_id=payload.tg_user_id,
        amount=payload.amount,
        comment=comment or None,
    )
    session.add(contribution)
    await session.commit()
    await session.refresh(contribution)
    return _budget_contribution_to_out(contribution)


async def create_expense(
    session: AsyncSession, payload: ExpenseCreate
) -> ExpenseCreateOut:
    if not await _user_exists(session, payload.tg_user_id):
        raise ValueError("user is not registered")

    category = payload.category.strip()
    if not category:
        raise ValueError("category cannot be empty")
    comment = payload.comment.strip() if payload.comment else None
    expense = Expense(
        tg_user_id=payload.tg_user_id,
        amount=payload.amount,
        category=category,
        spent_at=_ensure_timezone(payload.spent_at),
        comment=comment or None,
    )
    session.add(expense)
    await session.commit()
    await session.refresh(expense)
    spender_name = await _get_user_name(session, payload.tg_user_id)
    daily = await get_daily_limit_status(
        session,
        user_id=payload.tg_user_id,
        at=expense.spent_at,
    )
    return ExpenseCreateOut(
        expense=_expense_to_out(expense),
        spender_name=spender_name,
        daily=daily,
    )


async def list_expenses(
    session: AsyncSession,
    *,
    user_id: int | None = None,
    limit: int = 20,
) -> list[ExpenseOut]:
    query = select(Expense)
    if user_id is not None:
        query = query.where(Expense.tg_user_id == user_id)
    query = query.order_by(Expense.spent_at.desc(), Expense.id.desc()).limit(
        max(1, min(limit, 100))
    )
    rows = (await session.execute(query)).scalars()
    return [_expense_to_out(item) for item in rows]


async def get_budget_summary(
    session: AsyncSession, *, user_id: int
) -> BudgetSummaryOut:
    total_income_raw = (
        await session.execute(
            select(func.coalesce(func.sum(BudgetContribution.amount), 0))
        )
    ).scalar_one()
    total_expense_raw = (
        await session.execute(select(func.coalesce(func.sum(Expense.amount), 0)))
    ).scalar_one()

    contributors_rows = await session.execute(
        select(
            BudgetContribution.tg_user_id,
            func.max(User.name),
            func.sum(BudgetContribution.amount),
        )
        .join(User, User.tg_user_id == BudgetContribution.tg_user_id)
        .group_by(BudgetContribution.tg_user_id)
        .order_by(func.sum(BudgetContribution.amount).desc())
    )
    spenders_rows = await session.execute(
        select(
            Expense.tg_user_id,
            func.max(User.name),
            func.sum(Expense.amount),
        )
        .join(User, User.tg_user_id == Expense.tg_user_id)
        .group_by(Expense.tg_user_id)
        .order_by(func.sum(Expense.amount).desc())
    )
    categories_rows = await session.execute(
        select(Expense.category, func.sum(Expense.amount))
        .group_by(Expense.category)
        .order_by(func.sum(Expense.amount).desc())
    )

    total_income = int(total_income_raw or 0)
    total_expense = int(total_expense_raw or 0)
    daily_status = await get_daily_limit_status(session, user_id=user_id)
    return BudgetSummaryOut(
        total_income=total_income,
        total_expense=total_expense,
        balance=total_income - total_expense,
        contributors=[
            BudgetContributorStats(
                tg_user_id=int(tg_user_id),
                name=name,
                amount=int(amount or 0),
            )
            for tg_user_id, name, amount in contributors_rows.all()
        ],
        spenders=[
            BudgetSpenderStats(
                tg_user_id=int(tg_user_id),
                name=name,
                amount=int(amount or 0),
            )
            for tg_user_id, name, amount in spenders_rows.all()
        ],
        categories=[
            BudgetCategoryStats(category=category, amount=int(amount or 0))
            for category, amount in categories_rows.all()
        ],
        daily=daily_status,
    )


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
