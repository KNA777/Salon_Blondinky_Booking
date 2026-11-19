"""add exclusion constraint against double-booking

Revision ID: a1b2c3d4e5f6
Revises: 34e07092e402
Create Date: 2026-11-19 14:20:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "34e07092e402"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Добавляем exclusion constraint: два appointments одного мастера не могут
    пересекаться по времени (tstzrange &&), если оба в блокирующих статусах
    (created / confirmed). Это защита от двойной записи на уровне БД (задача 9).

    Для tstzrange && нужен индекс-метод GiST поверх timestamp with time zone,
    который предоставляет расширение btree_gist.
    """
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.execute(
        """
        ALTER TABLE appointments
        ADD CONSTRAINT appointments_no_overlap
        EXCLUDE USING gist (
            master_id WITH =,
            tstzrange(starts_at, ends_at) WITH &&
        )
        WHERE (status IN ('created', 'confirmed'))
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE appointments DROP CONSTRAINT IF EXISTS appointments_no_overlap"
    )
