"""unique transactions.payment_id

Revision ID: 0014_payment_id_unique
Revises: 0013_ride_template_hidden
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014_payment_id_unique"
down_revision: str | Sequence[str] | None = "0013_ride_template_hidden"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_transactions_payment_id", table_name="transactions")
    op.create_index("ix_transactions_payment_id", "transactions", ["payment_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_transactions_payment_id", table_name="transactions")
    op.create_index("ix_transactions_payment_id", "transactions", ["payment_id"], unique=False)
