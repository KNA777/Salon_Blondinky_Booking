"""Проверка конфликта слотов (защита от двойной записи, задача 9).

Два уровня защиты:
1. Приложение: перед созданием записи проверяем, нет ли уже записей того же мастера
   в блокирующих статусах (created/confirmed), пересекающихся с запрашиваемым интервалом.
   Это быстрый отказ без гонки и понятная ошибка.
2. БД: exclusion constraint (appointments_no_overlap, миграция a1b2c3d4e5f6) не даёт
   двум одновременным транзакциям вставить пересекающиеся записи — даже если проверка
   на уровне приложения «разошлась» из-за гонки.

Чистая функция overlaps() вынесена отдельно, чтобы её можно было тестировать без БД.
"""

from datetime import datetime

from app.models import AppointmentStatusEnum

# Статусы, занимающие время мастера. Один источник правды: slots.py тоже импортирует
# этот список отсюда (см. BLOCKING_STATUSES ниже), чтобы статусы не разъехались.
BLOCKING_STATUSES = [
    AppointmentStatusEnum.CREATED,
    AppointmentStatusEnum.CONFIRMED,
]


def overlaps(
    a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime
) -> bool:
    """Пересечение двух полуинтервалов [start, end)."""
    return a_start < b_end and a_end > b_start


def has_conflict(
    appointments: list[tuple[datetime, datetime]],
    new_start: datetime,
    new_end: datetime,
) -> bool:
    """Есть ли пересечение нового интервала хотя бы с одним из существующих.

    appointments — список (starts_at, ends_at) существующих занятых интервалов.
    """
    return any(overlaps(new_start, new_end, s, e) for s, e in appointments)
