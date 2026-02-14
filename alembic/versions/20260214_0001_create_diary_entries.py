"""create diary entries table

Revision ID: 20260214_0001
Revises:
Create Date: 2026-02-14 14:30:00
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260214_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diary_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tg_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.Text(), nullable=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_diary_entries_chat_id", "diary_entries", ["chat_id"], unique=False
    )
    op.create_index(
        "ix_diary_entries_tg_user_id", "diary_entries", ["tg_user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_diary_entries_tg_user_id", table_name="diary_entries")
    op.drop_index("ix_diary_entries_chat_id", table_name="diary_entries")
    op.drop_table("diary_entries")
