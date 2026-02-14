"""create user settings table

Revision ID: 20260214_0003
Revises: 20260214_0002
Create Date: 2026-02-14 16:10:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260214_0003"
down_revision = "20260214_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_settings",
        sa.Column("tg_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "timezone", sa.Text(), server_default=sa.text("'UTC'"), nullable=False
        ),
        sa.PrimaryKeyConstraint("tg_user_id"),
    )


def downgrade() -> None:
    op.drop_table("user_settings")
