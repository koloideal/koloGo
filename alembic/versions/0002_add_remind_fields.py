"""add remind_minutes and remind_sent to rides

Revision ID: 0002_add_remind_fields
Revises: 0001_initial
Create Date: 2025-09-05
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_add_remind_fields"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rides",
        sa.Column("remind_minutes", sa.Integer(), nullable=False, server_default="30"),
    )
    op.add_column(
        "rides",
        sa.Column("remind_sent", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("rides", "remind_sent")
    op.drop_column("rides", "remind_minutes")
