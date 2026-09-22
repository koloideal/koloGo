"""add origin and destination to rides

Revision ID: 0009_add_ride_locations
Revises: 0008_add_payment_fields
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_add_ride_locations"
down_revision: str | Sequence[str] | None = "0008_add_payment_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("rides", sa.Column("origin", sa.String(length=128), nullable=True))
    op.add_column("rides", sa.Column("destination", sa.String(length=128), nullable=True))
    op.execute("UPDATE rides SET origin = 'Новое Поле', destination = 'Минск'")
    op.alter_column("rides", "origin", nullable=False)
    op.alter_column("rides", "destination", nullable=False)


def downgrade() -> None:
    op.drop_column("rides", "destination")
    op.drop_column("rides", "origin")
