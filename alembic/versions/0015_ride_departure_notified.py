"""add ride departure_notified

Revision ID: 0015_departure_notified
Revises: 0014_payment_id_unique
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_departure_notified"
down_revision: str | Sequence[str] | None = "0014_payment_id_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rides",
        sa.Column("departure_notified", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("rides", "departure_notified")
