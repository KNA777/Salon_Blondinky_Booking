"""add reminder markers to appointments

Revision ID: 9a1b2c3d4e5f
Revises: 7c9d1e2f3a4b
Create Date: 2026-11-20 19:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "9a1b2c3d4e5f"
down_revision: Union[str, Sequence[str], None] = "7c9d1e2f3a4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Добавляем маркеры отправленных напоминаний (24ч/2ч) для идемпотентности рассылки."""
    op.add_column(
        "appointments",
        sa.Column("reminded_24h_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "appointments",
        sa.Column("reminded_2h_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("appointments", "reminded_2h_at")
    op.drop_column("appointments", "reminded_24h_at")
