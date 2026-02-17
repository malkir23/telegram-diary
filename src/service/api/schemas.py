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


class BudgetContributionCreate(BaseModel):
    tg_user_id: int = Field(ge=1)
    amount: int = Field(gt=0)
    comment: str | None = Field(default=None, max_length=1024)


class BudgetContributionOut(BaseModel):
    id: int
    tg_user_id: int
    amount: int
    comment: str | None
    created_at: datetime


class ExpenseCreate(BaseModel):
    tg_user_id: int = Field(ge=1)
    amount: int = Field(gt=0)
    category: str = Field(min_length=1, max_length=255)
    spent_at: datetime
    comment: str | None = Field(default=None, max_length=1024)


class ExpenseOut(BaseModel):
    id: int
    tg_user_id: int
    amount: int
    category: str
    spent_at: datetime
    comment: str | None
    created_at: datetime


class DailyLimitStatusOut(BaseModel):
    date: str
    timezone: str
    daily_limit: int | None
    spent: int
    remaining: int | None
    exceeded: bool
    exceeded_by: int


class ExpenseCreateOut(BaseModel):
    expense: ExpenseOut
    spender_name: str | None
    daily: DailyLimitStatusOut


class BudgetDailyLimitSet(BaseModel):
    actor_tg_user_id: int = Field(ge=1)
    daily_limit: int = Field(ge=0)


class BudgetDailyLimitOut(BaseModel):
    daily_limit: int | None
    updated_by_tg_user_id: int | None
    updated_at: datetime | None


class BudgetContributorStats(BaseModel):
    tg_user_id: int
    name: str | None
    amount: int


class BudgetSpenderStats(BaseModel):
    tg_user_id: int
    name: str | None
    amount: int


class BudgetCategoryStats(BaseModel):
    category: str
    amount: int


class BudgetSummaryOut(BaseModel):
    total_income: int
    total_expense: int
    balance: int
    contributors: list[BudgetContributorStats]
    spenders: list[BudgetSpenderStats]
    categories: list[BudgetCategoryStats]
    daily: DailyLimitStatusOut
