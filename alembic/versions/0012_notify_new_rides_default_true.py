"""notify_new_rides default true for new users

Revision ID: 0012_notify_default_true
Revises: 0011_ride_track_max_speed
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_notify_default_true"
down_revision: str | Sequence[str] | None = "0011_ride_track_max_speed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "notify_new_rides", server_default=sa.text("true"))


def downgrade() -> None:
    op.alter_column("users", "notify_new_rides", server_default=sa.text("false"))
