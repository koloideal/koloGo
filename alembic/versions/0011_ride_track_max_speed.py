"""add ride track max speed

Revision ID: 0011_ride_track_max_speed
Revises: 0010_add_geo_tracking
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_ride_track_max_speed"
down_revision: str | Sequence[str] | None = "0010_add_geo_tracking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rides",
        sa.Column("track_max_speed_mps", sa.Float(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("rides", "track_max_speed_mps")
