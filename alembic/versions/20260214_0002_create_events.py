"""create events tables

Revision ID: 20260214_0002
Revises: 20260214_0001
Create Date: 2026-02-14 15:20:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260214_0002"
down_revision = "20260214_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("creator_tg_user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "reminder_sent",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_events_creator_tg_user_id", "events", ["creator_tg_user_id"], unique=False
    )
    op.create_index("ix_events_start_at", "events", ["start_at"], unique=False)

    op.create_table(
        "event_participants",
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("tg_user_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id", "tg_user_id"),
    )
    op.create_index(
        "ix_event_participants_tg_user_id",
        "event_participants",
        ["tg_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_event_participants_tg_user_id", table_name="event_participants")
    op.drop_table("event_participants")
    op.drop_index("ix_events_start_at", table_name="events")
    op.drop_index("ix_events_creator_tg_user_id", table_name="events")
    op.drop_table("events")
