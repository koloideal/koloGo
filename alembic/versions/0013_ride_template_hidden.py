"""add ride template_hidden

Revision ID: 0013_ride_template_hidden
Revises: 0012_notify_default_true
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_ride_template_hidden"
down_revision: str | Sequence[str] | None = "0012_notify_default_true"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rides",
        sa.Column("template_hidden", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("rides", "template_hidden")
