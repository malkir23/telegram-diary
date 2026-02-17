"""create budget settings table

Revision ID: 20260217_0007
Revises: 20260217_0006
Create Date: 2026-02-17 17:40:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260217_0007"
down_revision = "20260217_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "budget_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("daily_limit", sa.Integer(), nullable=True),
        sa.Column("updated_by_tg_user_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_tg_user_id"],
            ["users.tg_user_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("INSERT INTO budget_settings (id, daily_limit) VALUES (1, NULL)")


def downgrade() -> None:
    op.drop_table("budget_settings")
