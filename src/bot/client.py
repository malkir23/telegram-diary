from __future__ import annotations

from datetime import datetime

import aiohttp

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
)


class ServiceConflictError(RuntimeError):
    def __init__(self, conflicts: list[ConflictItem]) -> None:
        super().__init__("Conflict detected")
        self.conflicts = conflicts


class DiaryServiceClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8080") -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=15)

    async def _json_request(
        self,
        session: aiohttp.ClientSession,
        method: str,
        path: str,
        *,
        json_payload: dict | None = None,
        params: dict | None = None,
    ) -> dict | list:
        async with session.request(
            method,
            f"{self._base_url}{path}",
            json=json_payload,
            params=params,
            timeout=self._timeout,
        ) as response:
            data = await response.json(content_type=None)
            if response.status == 409:
                conflicts = [
                    ConflictItem(
                        event_id=item["event_id"],
                        title=item["title"],
                        start_at=datetime.fromisoformat(item["start_at"]),
                        end_at=datetime.fromisoformat(item["end_at"]),
                        conflicting_participants=item["conflicting_participants"],
                    )
                    for item in data.get("conflicts", [])
                ]
                raise ServiceConflictError(conflicts)
            if response.status >= 400:
                raise RuntimeError(f"Service error {response.status}: {data}")
            return data

    async def save_entry(
        self, session: aiohttp.ClientSession, entry: DiaryEntryCreate
    ) -> None:
        await self._json_request(
            session,
            "POST",
            "/diary-entries",
            json_payload={
                "tg_user_id": entry.tg_user_id,
                "username": entry.username,
                "chat_id": entry.chat_id,
                "message_id": entry.message_id,
                "text": entry.text,
            },
        )

    async def list_entries(
        self, session: aiohttp.ClientSession, user_id: int
    ) -> list[DiaryEntryOut]:
        data = await self._json_request(
            session,
            "GET",
            "/diary-entries",
            params={"user_id": str(user_id)},
        )
        result: list[DiaryEntryOut] = []
        for row in data:
            result.append(
                DiaryEntryOut(
                    id=row["id"],
                    tg_user_id=row["tg_user_id"],
                    username=row["username"],
                    chat_id=row["chat_id"],
                    message_id=row["message_id"],
                    text=row["text"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
            )
        return result

    async def update_entry(
        self,
        session: aiohttp.ClientSession,
        entry_id: int,
        payload: DiaryEntryUpdate,
    ) -> DiaryEntryOut:
        data = await self._json_request(
            session,
            "PUT",
            f"/diary-entries/{entry_id}",
            json_payload={
                "actor_tg_user_id": payload.actor_tg_user_id,
                "text": payload.text,
            },
        )
        return DiaryEntryOut(
            id=data["id"],
            tg_user_id=data["tg_user_id"],
            username=data["username"],
            chat_id=data["chat_id"],
            message_id=data["message_id"],
            text=data["text"],
            created_at=datetime.fromisoformat(data["created_at"]),
        )

    async def delete_entry(
        self,
        session: aiohttp.ClientSession,
        entry_id: int,
        payload: DiaryEntryDelete,
    ) -> None:
        await self._json_request(
            session,
            "DELETE",
            f"/diary-entries/{entry_id}",
            json_payload={"actor_tg_user_id": payload.actor_tg_user_id},
        )

    async def create_event(
        self, session: aiohttp.ClientSession, event: EventCreate
    ) -> EventOut:
        data = await self._json_request(
            session,
            "POST",
            "/events",
            json_payload={
                "creator_tg_user_id": event.creator_tg_user_id,
                "title": event.title,
                "start_at": event.start_at.isoformat(),
                "end_at": event.end_at.isoformat(),
                "participants": event.participants,
            },
        )
        return EventOut(
            id=data["id"],
            creator_tg_user_id=data["creator_tg_user_id"],
            title=data["title"],
            start_at=datetime.fromisoformat(data["start_at"]),
            end_at=datetime.fromisoformat(data["end_at"]),
            participants=data["participants"],
        )

    async def update_event(
        self,
        session: aiohttp.ClientSession,
        event_id: int,
        event: EventUpdate,
    ) -> EventOut:
        data = await self._json_request(
            session,
            "PUT",
            f"/events/{event_id}",
            json_payload={
                "actor_tg_user_id": event.actor_tg_user_id,
                "title": event.title,
                "start_at": event.start_at.isoformat(),
                "end_at": event.end_at.isoformat(),
                "participants": event.participants,
            },
        )
        return EventOut(
            id=data["id"],
            creator_tg_user_id=data["creator_tg_user_id"],
            title=data["title"],
            start_at=datetime.fromisoformat(data["start_at"]),
            end_at=datetime.fromisoformat(data["end_at"]),
            participants=data["participants"],
        )

    async def delete_event(
        self, session: aiohttp.ClientSession, event_id: int, payload: EventDelete
    ) -> None:
        await self._json_request(
            session,
            "DELETE",
            f"/events/{event_id}",
            json_payload={"actor_tg_user_id": payload.actor_tg_user_id},
        )

    async def list_events(
        self,
        session: aiohttp.ClientSession,
        user_id: int,
    ) -> list[EventOut]:
        data = await self._json_request(
            session,
            "GET",
            "/events",
            params={"user_id": str(user_id)},
        )
        items: list[EventOut] = []
        for row in data:
            items.append(
                EventOut(
                    id=row["id"],
                    creator_tg_user_id=row["creator_tg_user_id"],
                    title=row["title"],
                    start_at=datetime.fromisoformat(row["start_at"]),
                    end_at=datetime.fromisoformat(row["end_at"]),
                    participants=row["participants"],
                )
            )
        return items

    async def claim_due_reminders(
        self, session: aiohttp.ClientSession
    ) -> list[ReminderOut]:
        data = await self._json_request(
            session, "POST", "/events/reminders/claim", json_payload={}
        )
        reminders: list[ReminderOut] = []
        for row in data:
            reminders.append(
                ReminderOut(
                    event_id=row["event_id"],
                    recipients=row["recipients"],
                    title=row["title"],
                    start_at=datetime.fromisoformat(row["start_at"]),
                )
            )
        return reminders

    async def mark_reminder_sent(
        self, session: aiohttp.ClientSession, event_id: int
    ) -> None:
        await self._json_request(
            session,
            "POST",
            f"/events/{event_id}/reminder-sent",
            json_payload={},
        )

    async def add_budget_contribution(
        self,
        session: aiohttp.ClientSession,
        payload: BudgetContributionCreate,
    ) -> BudgetContributionOut:
        data = await self._json_request(
            session,
            "POST",
            "/budget/contributions",
            json_payload={
                "tg_user_id": payload.tg_user_id,
                "amount": payload.amount,
                "comment": payload.comment,
            },
        )
        return BudgetContributionOut(
            id=data["id"],
            tg_user_id=data["tg_user_id"],
            amount=data["amount"],
            comment=data["comment"],
            created_at=datetime.fromisoformat(data["created_at"]),
        )

    async def add_expense(
        self,
        session: aiohttp.ClientSession,
        payload: ExpenseCreate,
    ) -> ExpenseCreateOut:
        data = await self._json_request(
            session,
            "POST",
            "/budget/expenses",
            json_payload={
                "tg_user_id": payload.tg_user_id,
                "amount": payload.amount,
                "category": payload.category,
                "spent_at": payload.spent_at.isoformat(),
                "comment": payload.comment,
            },
        )
        expense_data = data["expense"]
        daily_data = data["daily"]
        return ExpenseCreateOut(
            expense=ExpenseOut(
                id=expense_data["id"],
                tg_user_id=expense_data["tg_user_id"],
                amount=expense_data["amount"],
                category=expense_data["category"],
                spent_at=datetime.fromisoformat(expense_data["spent_at"]),
                comment=expense_data["comment"],
                created_at=datetime.fromisoformat(expense_data["created_at"]),
            ),
            spender_name=data["spender_name"],
            daily=DailyLimitStatusOut(
                date=daily_data["date"],
                timezone=daily_data["timezone"],
                daily_limit=daily_data["daily_limit"],
                spent=daily_data["spent"],
                remaining=daily_data["remaining"],
                exceeded=daily_data["exceeded"],
                exceeded_by=daily_data["exceeded_by"],
            ),
        )

    async def get_budget_summary(
        self,
        session: aiohttp.ClientSession,
        *,
        user_id: int,
    ) -> BudgetSummaryOut:
        data = await self._json_request(
            session,
            "GET",
            "/budget/summary",
            params={"user_id": str(user_id)},
        )
        daily_data = data["daily"]
        return BudgetSummaryOut(
            total_income=data["total_income"],
            total_expense=data["total_expense"],
            balance=data["balance"],
            contributors=[
                BudgetContributorStats(
                    tg_user_id=item["tg_user_id"],
                    name=item["name"],
                    amount=item["amount"],
                )
                for item in data["contributors"]
            ],
            spenders=[
                BudgetSpenderStats(
                    tg_user_id=item["tg_user_id"],
                    name=item["name"],
                    amount=item["amount"],
                )
                for item in data["spenders"]
            ],
            categories=[
                BudgetCategoryStats(
                    category=item["category"],
                    amount=item["amount"],
                )
                for item in data["categories"]
            ],
            daily=DailyLimitStatusOut(
                date=daily_data["date"],
                timezone=daily_data["timezone"],
                daily_limit=daily_data["daily_limit"],
                spent=daily_data["spent"],
                remaining=daily_data["remaining"],
                exceeded=daily_data["exceeded"],
                exceeded_by=daily_data["exceeded_by"],
            ),
        )

    async def list_expenses(
        self,
        session: aiohttp.ClientSession,
        *,
        user_id: int | None = None,
        limit: int = 20,
    ) -> list[ExpenseOut]:
        params = {"limit": str(limit)}
        if user_id is not None:
            params["user_id"] = str(user_id)
        data = await self._json_request(
            session,
            "GET",
            "/budget/expenses",
            params=params,
        )
        return [
            ExpenseOut(
                id=item["id"],
                tg_user_id=item["tg_user_id"],
                amount=item["amount"],
                category=item["category"],
                spent_at=datetime.fromisoformat(item["spent_at"]),
                comment=item["comment"],
                created_at=datetime.fromisoformat(item["created_at"]),
            )
            for item in data
        ]

    async def get_daily_limit(
        self, session: aiohttp.ClientSession
    ) -> BudgetDailyLimitOut:
        data = await self._json_request(session, "GET", "/budget/daily-limit")
        updated_at_raw = data.get("updated_at")
        return BudgetDailyLimitOut(
            daily_limit=data["daily_limit"],
            updated_by_tg_user_id=data["updated_by_tg_user_id"],
            updated_at=(
                datetime.fromisoformat(updated_at_raw) if updated_at_raw else None
            ),
        )

    async def set_daily_limit(
        self,
        session: aiohttp.ClientSession,
        payload: BudgetDailyLimitSet,
    ) -> BudgetDailyLimitOut:
        data = await self._json_request(
            session,
            "PUT",
            "/budget/daily-limit",
            json_payload={
                "actor_tg_user_id": payload.actor_tg_user_id,
                "daily_limit": payload.daily_limit,
            },
        )
        updated_at_raw = data.get("updated_at")
        return BudgetDailyLimitOut(
            daily_limit=data["daily_limit"],
            updated_by_tg_user_id=data["updated_by_tg_user_id"],
            updated_at=(
                datetime.fromisoformat(updated_at_raw) if updated_at_raw else None
            ),
        )

    async def get_daily_status(
        self,
        session: aiohttp.ClientSession,
        *,
        user_id: int,
    ) -> DailyLimitStatusOut:
        data = await self._json_request(
            session,
            "GET",
            "/budget/daily-status",
            params={"user_id": str(user_id)},
        )
        return DailyLimitStatusOut(
            date=data["date"],
            timezone=data["timezone"],
            daily_limit=data["daily_limit"],
            spent=data["spent"],
            remaining=data["remaining"],
            exceeded=data["exceeded"],
            exceeded_by=data["exceeded_by"],
        )

    async def get_user_timezone(
        self, session: aiohttp.ClientSession, user_id: int
    ) -> UserTimezoneOut:
        data = await self._json_request(session, "GET", f"/users/{user_id}/timezone")
        return UserTimezoneOut(tg_user_id=data["tg_user_id"], timezone=data["timezone"])

    async def set_user_timezone(
        self, session: aiohttp.ClientSession, user_id: int, timezone: str
    ) -> UserTimezoneOut:
        data = await self._json_request(
            session,
            "PUT",
            f"/users/{user_id}/timezone",
            json_payload={"timezone": timezone},
        )
        return UserTimezoneOut(tg_user_id=data["tg_user_id"], timezone=data["timezone"])

    async def upsert_user(
        self,
        session: aiohttp.ClientSession,
        user_id: int,
        *,
        name: str,
        tag: str | None,
    ) -> UserOut:
        data = await self._json_request(
            session,
            "PUT",
            f"/users/{user_id}",
            json_payload={"name": name, "tag": tag},
        )
        return UserOut(
            tg_user_id=data["tg_user_id"],
            name=data["name"],
            tag=data["tag"],
        )

    async def resolve_users(
        self, session: aiohttp.ClientSession, labels: list[str]
    ) -> UserResolveOut:
        data = await self._json_request(
            session,
            "GET",
            "/users/resolve",
            params={"labels": ",".join(labels)},
        )
        return UserResolveOut(resolved=data["resolved"], unresolved=data["unresolved"])
