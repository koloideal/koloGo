"""add payment fields to transactions

Revision ID: 0008_add_payment_fields
Revises: 0007_add_settings
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_add_payment_fields"
down_revision: str | Sequence[str] | None = "0007_add_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("payment_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("payment_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="completed",
            nullable=False,
        ),
    )
    op.create_index("ix_transactions_payment_id", "transactions", ["payment_id"])


def downgrade() -> None:
    op.drop_index("ix_transactions_payment_id", table_name="transactions")
    op.drop_column("transactions", "status")
    op.drop_column("transactions", "payment_url")
    op.drop_column("transactions", "payment_id")
