"""add vip_hold_minutes to rides

Revision ID: 0006_add_vip_hold_minutes
Revises: 0005_add_requisites
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_add_vip_hold_minutes"
down_revision: str | Sequence[str] | None = "0005_add_requisites"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rides",
        sa.Column(
            "vip_hold_minutes",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("rides", "vip_hold_minutes")
