"""migrate event participants to text labels

Revision ID: 20260214_0004
Revises: 20260214_0003
Create Date: 2026-02-14 16:45:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260214_0004"
down_revision = "20260214_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_event_participants_tg_user_id", table_name="event_participants")
    op.drop_table("event_participants")
    op.create_table(
        "event_participants",
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("participant_label", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id", "participant_label"),
    )
    op.create_index(
        "ix_event_participants_participant_label",
        "event_participants",
        ["participant_label"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_event_participants_participant_label", table_name="event_participants"
    )
    op.drop_table("event_participants")
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
