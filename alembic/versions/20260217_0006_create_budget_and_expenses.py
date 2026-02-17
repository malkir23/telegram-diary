"""create budget contributions and expenses

Revision ID: 20260217_0006
Revises: 20260214_0005
Create Date: 2026-02-17 16:45:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260217_0006"
down_revision = "20260214_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "budget_contributions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tg_user_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tg_user_id"], ["users.tg_user_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_budget_contributions_tg_user_id",
        "budget_contributions",
        ["tg_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_budget_contributions_created_at",
        "budget_contributions",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "expenses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tg_user_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("spent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tg_user_id"], ["users.tg_user_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_expenses_tg_user_id", "expenses", ["tg_user_id"], unique=False)
    op.create_index("ix_expenses_spent_at", "expenses", ["spent_at"], unique=False)
    op.create_index("ix_expenses_created_at", "expenses", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_expenses_created_at", table_name="expenses")
    op.drop_index("ix_expenses_spent_at", table_name="expenses")
    op.drop_index("ix_expenses_tg_user_id", table_name="expenses")
    op.drop_table("expenses")

    op.drop_index(
        "ix_budget_contributions_created_at",
        table_name="budget_contributions",
    )
    op.drop_index(
        "ix_budget_contributions_tg_user_id",
        table_name="budget_contributions",
    )
    op.drop_table("budget_contributions")
