"""add geo tracking: locations, ride track points, ride geo columns

Revision ID: 0010_add_geo_tracking
Revises: 0009_add_ride_locations
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_add_geo_tracking"
down_revision: str | Sequence[str] | None = "0009_add_ride_locations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "locations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "ride_track_points",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ride_id", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("recorded_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["ride_id"], ["rides.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_track_points_ride", "ride_track_points", ["ride_id"])
    op.add_column("rides", sa.Column("origin_lat", sa.Float(), nullable=True))
    op.add_column("rides", sa.Column("origin_lon", sa.Float(), nullable=True))
    op.add_column("rides", sa.Column("destination_lat", sa.Float(), nullable=True))
    op.add_column("rides", sa.Column("destination_lon", sa.Float(), nullable=True))
    op.add_column("rides", sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("rides", sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("rides", sa.Column("track_distance_m", sa.Float(), server_default="0", nullable=False))
    op.add_column("rides", sa.Column("live_chat_id", sa.BigInteger(), nullable=True))
    op.add_column("rides", sa.Column("live_message_id", sa.BigInteger(), nullable=True))
    op.add_column("rides", sa.Column("arrive_streak", sa.Integer(), server_default="0", nullable=False))
    op.add_column("rides", sa.Column("awaiting_live_geo", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("rides", "awaiting_live_geo")
    op.drop_column("rides", "arrive_streak")
    op.drop_column("rides", "live_message_id")
    op.drop_column("rides", "live_chat_id")
    op.drop_column("rides", "track_distance_m")
    op.drop_column("rides", "finished_at")
    op.drop_column("rides", "started_at")
    op.drop_column("rides", "destination_lon")
    op.drop_column("rides", "destination_lat")
    op.drop_column("rides", "origin_lon")
    op.drop_column("rides", "origin_lat")
    op.drop_table("ride_track_points")
    op.drop_table("locations")
