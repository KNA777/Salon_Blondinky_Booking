"""add client auth fields (password_hash, is_admin)

Revision ID: 7c9d1e2f3a4b
Revises: a1b2c3d4e5f6
Create Date: 2026-11-20 16:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "7c9d1e2f3a4b"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Добавляем поля учётной записи клиента: хеш пароля и флаг администратора."""
    op.add_column(
        "clients",
        sa.Column("password_hash", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "clients",
        sa.Column(
            "is_admin",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("clients", "is_admin")
    op.drop_column("clients", "password_hash")
