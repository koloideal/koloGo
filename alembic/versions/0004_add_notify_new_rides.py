"""add notify_new_rides to users

Revision ID: 0004_add_notify_new_rides
Revises: 62863d1ef523
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_add_notify_new_rides"
down_revision: str | Sequence[str] | None = "62863d1ef523"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "notify_new_rides",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "notify_new_rides")
