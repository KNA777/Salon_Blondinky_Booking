"""Контекстный менеджер БД: открывает сессию и репозитории на время операции.

`DBManager` — это точка входа в слой данных. Внутри одного HTTP-запроса или одного
апдейта бота живёт один `DBManager`, через который код получает доступ к репозиториям
(`services`, `masters`, `clients`, `appointments`, `working_hours`) — каждый обёрнут
вокруг одной общей асинхронной сессии SQLAlchemy.

Использование (`async with`):
    async with DBManager(session_factory) as db:
        service = await db.services.get_one_by_id(id=1)
        # db.commit() — зафиксировать изменения явно

`__aexit__` всегда делает rollback незакоммиченных изменений и закрывает сессию,
поэтому «утечь» открытая сессия не может даже при исключении в обработчике.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.patterns.repository.appointments import AppointmentRepository
from app.patterns.repository.clients import ClientRepository
from app.patterns.repository.masters import MasterRepository
from app.patterns.repository.payments import PaymentRepository
from app.patterns.repository.services import ServiceRepository
from app.patterns.repository.working_hours import WorkingHourRepository


class DBManager:
    """Открывает асинхронную сессию БД и предоставляет репозитории.

    Атрибуты:
      session_factory — фабрика асинхронных сессий (async_sessionmaker), создаётся один
          раз при старте приложения (lifespan в main.py или бот в app/bot/__main__.py).
      session — активная сессия (появляется после входа в `async with`).
      services / masters / working_hours / clients / appointments — репозитории,
          привязанные к этой сессии.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Сохраняет фабрику сессий. Сама сессия откроется при входе в `async with`."""
        self.session_factory: async_sessionmaker[AsyncSession] = session_factory

    async def __aenter__(self) -> "DBManager":
        """Открывает сессию и конструирует репозитории поверх неё."""
        self.session: AsyncSession = self.session_factory()

        self.services: ServiceRepository = ServiceRepository(self.session)
        self.masters: MasterRepository = MasterRepository(self.session)
        self.working_hours: WorkingHourRepository = WorkingHourRepository(self.session)
        self.clients: ClientRepository = ClientRepository(self.session)
        self.appointments: AppointmentRepository = AppointmentRepository(self.session)
        self.payments: PaymentRepository = PaymentRepository(self.session)

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Откатывает незакоммиченные изменения и закрывает сессию.

        Возвращает None (не подавляем исключение): ошибка распространится дальше,
        но сессия гарантированно освободится.
        """
        await self.session.rollback()
        await self.session.close()

    async def commit(self) -> None:
        """Фиксирует текущую транзакцию (подтверждает накопленные изменения)."""
        await self.session.commit()
