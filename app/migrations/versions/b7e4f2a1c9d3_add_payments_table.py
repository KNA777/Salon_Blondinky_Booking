"""add payments table

Revision ID: b7e4f2a1c9d3
Revises: 9a1b2c3d4e5f
Create Date: 2026-11-20 20:05:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b7e4f2a1c9d3"
down_revision: Union[str, Sequence[str], None] = "9a1b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Таблица предоплат (задача 18, каркас)."""
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "appointment_id",
            sa.Integer(),
            sa.ForeignKey("appointments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("provider_payment_id", sa.String(length=128), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="telegram_payments"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("payments")
