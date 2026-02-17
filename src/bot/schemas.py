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
class DiaryEntryOut:
    id: int
    tg_user_id: int
    username: str | None
    chat_id: int
    message_id: int
    text: str
    created_at: datetime


@dataclass(slots=True)
class DiaryEntryUpdate:
    actor_tg_user_id: int
    text: str


@dataclass(slots=True)
class DiaryEntryDelete:
    actor_tg_user_id: int


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


@dataclass(slots=True)
class BudgetContributionCreate:
    tg_user_id: int
    amount: int
    comment: str | None


@dataclass(slots=True)
class BudgetContributionOut:
    id: int
    tg_user_id: int
    amount: int
    comment: str | None
    created_at: datetime


@dataclass(slots=True)
class ExpenseCreate:
    tg_user_id: int
    amount: int
    category: str
    spent_at: datetime
    comment: str | None


@dataclass(slots=True)
class ExpenseOut:
    id: int
    tg_user_id: int
    amount: int
    category: str
    spent_at: datetime
    comment: str | None
    created_at: datetime


@dataclass(slots=True)
class DailyLimitStatusOut:
    date: str
    timezone: str
    daily_limit: int | None
    spent: int
    remaining: int | None
    exceeded: bool
    exceeded_by: int


@dataclass(slots=True)
class ExpenseCreateOut:
    expense: ExpenseOut
    spender_name: str | None
    daily: DailyLimitStatusOut


@dataclass(slots=True)
class BudgetDailyLimitSet:
    actor_tg_user_id: int
    daily_limit: int


@dataclass(slots=True)
class BudgetDailyLimitOut:
    daily_limit: int | None
    updated_by_tg_user_id: int | None
    updated_at: datetime | None


@dataclass(slots=True)
class BudgetContributorStats:
    tg_user_id: int
    name: str | None
    amount: int


@dataclass(slots=True)
class BudgetSpenderStats:
    tg_user_id: int
    name: str | None
    amount: int


@dataclass(slots=True)
class BudgetCategoryStats:
    category: str
    amount: int


@dataclass(slots=True)
class BudgetSummaryOut:
    total_income: int
    total_expense: int
    balance: int
    contributors: list[BudgetContributorStats]
    spenders: list[BudgetSpenderStats]
    categories: list[BudgetCategoryStats]
    daily: DailyLimitStatusOut
