"""create users table and migrate event participants to telegram ids

Revision ID: 20260214_0005
Revises: 20260214_0004
Create Date: 2026-02-14 23:45:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260214_0005"
down_revision = "20260214_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("tg_user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("tag", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("tg_user_id"),
    )
    op.create_index("ix_users_tag", "users", ["tag"], unique=True)

    op.execute(
        """
        INSERT INTO users (tg_user_id, name, tag)
        SELECT DISTINCT d.tg_user_id, COALESCE(NULLIF(TRIM(d.username), ''), d.tg_user_id::text), LOWER(NULLIF(TRIM(d.username), ''))
        FROM diary_entries d
        ON CONFLICT (tg_user_id) DO UPDATE
        SET
            name = EXCLUDED.name,
            tag = COALESCE(EXCLUDED.tag, users.tag)
        """
    )
    op.execute(
        """
        INSERT INTO users (tg_user_id, name, tag)
        SELECT DISTINCT e.creator_tg_user_id, e.creator_tg_user_id::text, NULL
        FROM events e
        ON CONFLICT (tg_user_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO users (tg_user_id, name, tag)
        SELECT DISTINCT s.tg_user_id, s.tg_user_id::text, NULL
        FROM user_settings s
        ON CONFLICT (tg_user_id) DO NOTHING
        """
    )

    op.create_table(
        "event_participants_new",
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("participant_tg_user_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["participant_tg_user_id"], ["users.tg_user_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("event_id", "participant_tg_user_id"),
    )
    op.create_index(
        "ix_event_participants_participant_tg_user_id",
        "event_participants_new",
        ["participant_tg_user_id"],
        unique=False,
    )
    op.execute(
        """
        INSERT INTO event_participants_new (event_id, participant_tg_user_id)
        SELECT DISTINCT ep.event_id, u.tg_user_id
        FROM event_participants ep
        JOIN users u
          ON LOWER(COALESCE(u.tag, '')) = ep.participant_label
          OR LOWER(u.name) = ep.participant_label
        """
    )

    op.drop_index(
        "ix_event_participants_participant_label", table_name="event_participants"
    )
    op.drop_table("event_participants")
    op.rename_table("event_participants_new", "event_participants")


def downgrade() -> None:
    op.create_table(
        "event_participants_old",
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("participant_label", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id", "participant_label"),
    )
    op.create_index(
        "ix_event_participants_participant_label",
        "event_participants_old",
        ["participant_label"],
        unique=False,
    )
    op.execute(
        """
        INSERT INTO event_participants_old (event_id, participant_label)
        SELECT ep.event_id, COALESCE(u.tag, ep.participant_tg_user_id::text)
        FROM event_participants ep
        LEFT JOIN users u ON u.tg_user_id = ep.participant_tg_user_id
        """
    )
    op.drop_index(
        "ix_event_participants_participant_tg_user_id", table_name="event_participants"
    )
    op.drop_table("event_participants")
    op.rename_table("event_participants_old", "event_participants")

    op.drop_index("ix_users_tag", table_name="users")
    op.drop_table("users")
