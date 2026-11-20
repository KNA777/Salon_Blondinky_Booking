# Salon Booking

Запись клиентов в салон красоты: REST API на FastAPI + Telegram-бот (aiogram).

Клиент видит свободные слоты, выбирает мастера и услугу, записывается и управляет своей
записью. Бот ведёт диалог записи по шагам (FSM), API — полный набор операций над
услугами, мастерами, рабочими часами, клиентами и записями.

## Технологии

- **FastAPI** + Uvicorn — REST API и автодокументация (`/docs`).
- **SQLAlchemy (async)** + **asyncpg** — слой данных, асинхронный.
- **PostgreSQL** — основное хранилище; миграции через **Alembic**.
- **Redis** — хранение FSM-состояния бота в webhook-режиме (доступно из любого воркера).
- **aiogram 3** — Telegram-бот (polling или webhook).
- **pydantic-settings** — конфигурация из переменных окружения.
- **PyJWT** + **bcrypt** — аутентификация: JWT access-токены и хеширование паролей.
- **pytest** + **pytest-asyncio** — тесты; **Ruff** — линтер/форматтер.
- **uv** — менеджер зависимостей и окружения; **Docker Compose** — локальная инфраструктура.

## Возможности (готово на текущий момент)

- CRUD по услугам, мастерам, рабочим часам, клиентам, записям.
- Поиск свободных слотов мастера: `GET /masters/{id}/free-slots`.
- Машина переходов статусов записи с явным графом допустимых переходов.
- Защита от двойной записи: проверка конфликта на уровне приложения **и**
  exclusion-constraint в PostgreSQL.
- Отмена (`/cancel`) и перенос (`/reschedule`) записи.
- Аутентификация: регистрация и вход по паролю, выдача JWT access-токенов (bcrypt + PyJWT).
- Проверка владения записью: клиент управляет только своими записями, администратор — любыми.
- Telegram-бот с пошаговым сценарием записи (FSM), в двух режимах: long polling и webhook.
- Webhook с проверкой секрета (`X-Telegram-Bot-Api-Secret-Token`) — от поддельных запросов.

## Статусы записи и разрешённые переходы

```
created   -> confirmed | cancelled | no_show | completed
confirmed -> completed | no_show | cancelled
completed, no_show, cancelled — конечные (никуда не переводятся)
```

Граф задан в одном месте — `app/services/status_machine.py`. Запрещённый переход
(например, `completed -> created`) возвращает `HTTP 409`.

## Требования

- Python **>= 3.12**
- [uv](https://docs.astral.sh/uv/) — для локальной разработки
- Docker + Docker Compose — для Postgres и Redis
- Telegram-бот токен от [@BotFather](https://t.me/BotFather) — только для запуска бота

## Быстрый старт

### 1. Настройка окружения

```bash
cp .env.example .env
# отредактируйте .env: задайте POSTGRES_PASSWORD (и BOT_TOKEN, если нужен бот)
```

### 2. Поднять инфраструктуру (Postgres + Redis + API)

```bash
docker compose up --build
```

При старте API автоматически применяет миграции (`alembic upgrade head`).

Проверка:

- http://localhost:8000/health → `{"status":"ok","postgres":"ok","redis":"ok"}`
- http://localhost:8000/docs → автодокументация API (Swagger)

Остановить: `Ctrl+C`, затем `docker compose down` (данные сохранятся в томе `pgdata`;
чтобы удалить и их — `docker compose down -v`).

### 3. Запуск Telegram-бота (long polling)

```bash
uv sync                 # один раз: создать .venv и поставить зависимости
uv run python -m app.bot
```

Бот берёт токен из `BOT_TOKEN` в `.env` и уходит в long polling.

## Переменные окружения

Все настройки описаны в `app/core/config.py`. Полный список (в `.env.example` — только базовые):

| Переменная | Назначение | Обязательна |
| --- | --- | --- |
| `POSTGRES_USER` | пользователь Postgres | да |
| `POSTGRES_PASSWORD` | пароль Postgres | да |
| `POSTGRES_DB` | имя базы данных | да |
| `POSTGRES_HOST` | хост Postgres (`db` внутри Compose, `localhost` иначе) | да |
| `POSTGRES_PORT` | порт Postgres | да |
| `REDIS_HOST` | хост Redis (`redis` внутри Compose) | да |
| `REDIS_PORT` | порт Redis | да |
| `SALON_TIMEZONE` | часовой пояс салона (по умолчанию `Europe/Moscow`) | нет |
| `BOT_TOKEN` | токен Telegram-бота от @BotFather | для бота |
| `WEBHOOK_URL` | публичный URL webhook (включает webhook-режим) | для webhook |
| `WEBHOOK_SECRET` | секрет подписи webhook (придумываете сами) | для webhook |
| `JWT_SECRET_KEY` | ключ подписи JWT-токенов (в проде — длинная случайная строка) | нет (есть dev-дефолт) |
| `JWT_ALGORITHM` | алгоритм подписи токена (по умолчанию `HS256`) | нет |
| `JWT_EXPIRE_MINUTES` | время жизни access-токена в минутах (по умолчанию 1440) | нет |

## Аутентификация и владение записью

Пароли клиентов хранятся только как bcrypt-хеш, аутентификация — по JWT access-токенам.

- `POST /auth/register` — создать клиента с паролем, вернуть токен.
- `POST /auth/login` — вход по телефону и паролю, вернуть токен.

Дальше токен передаётся в заголовке `Authorization: Bearer <token>`. Зависимость
`get_current_client` (в `app/api/deps.py`) расшифровывает его и выдаёт текущего клиента.

**Владение записью**: клиент может отменять (`/cancel`) и переносить (`/reschedule`) только
свои записи — проверка идёт по `client_id`. Клиент с флагом `is_admin = true` управляет
любыми записями. Попытка управлять чужой записью возвращает `HTTP 403`.

## Webhook-режим бота

По умолчанию бот работает через long polling (`python -m app.bot`). Для webhook-режима
задайте `WEBHOOK_URL` и `WEBHOOK_SECRET` в `.env` — тогда Dispatcher поднимется внутри
FastAPI, а FSM-состояние будет храниться в Redis.

Из BotFather нужен только **токен бота**. Секрет (`WEBHOOK_SECRET`) придумываете сами —
это произвольная строка, которой Telegram подписывает запросы; она сверяется в заголовке
`X-Telegram-Bot-Api-Secret-Token`.

Регистрация webhook через Telegram Bot API:

```
https://api.telegram.org/bot<ТОКЕН>/setWebhook?url=<PUBLIC_URL>/webhook/bot&secret_token=<WEBHOOK_SECRET>
```

Для локальной разработки `PUBLIC_URL` обычно даёт туннель (ngrok / cloudflared / serveo).
Эндпоинт приёма апдейтов: `POST /webhook/bot` (неверный секрет → 403, бот не настроен → 503).

## Основные эндпоинты API

| Метод/путь | Описание |
| --- | --- |
| `GET /health` | проверка БД и Redis |
| `POST /auth/register` | регистрация клиента (вернёт JWT) |
| `POST /auth/login` | вход (вернёт JWT) |
| `GET/POST /services` | список / создать услугу |
| `GET/POST /masters` | список / создать мастера |
| `GET /masters/{id}/free-slots` | свободные слоты мастера |
| `GET/POST /masters/{id}/working-hours` | рабочие часы мастера |
| `PATCH/DELETE /masters/{id}/working-hours/{hid}` | изменить / удалить рабочие часы |
| `GET/POST /clients` | список / создать клиента (upsert по telegram_id) |
| `GET/POST /appointments` | список / создать запись |
| `GET/PATCH /appointments/{id}` | получить / изменить запись |
| `POST /appointments/{id}/status` | сменить статус (через машину) |
| `POST /appointments/{id}/cancel` | отменить запись |
| `POST /appointments/{id}/reschedule` | перенести запись |
| `POST /webhook/bot` | приём апдейтов Telegram (webhook) |

## Разработка

```bash
uv sync               # создать .venv и поставить зависимости (коммитим uv.lock)
uv run pytest         # тесты
uv run ruff check .   # линтер
uv run ruff format .  # форматирование
```

Миграции находятся в `app/migrations/`, генерируются и управляются Alembic.

## Структура проекта

```
app/
  main.py                  # создание FastAPI, lifespan, обработчики ошибок
  core/
    config.py              # настройки из переменных окружения (pydantic-settings)
    exceptions.py          # доменные исключения (NotFoundError, SlotConflictError, ...)
    security.py            # bcrypt-хеширование паролей и выпуск/проверка JWT
    db_context_manager.py  # контекстный менеджер сессии БД
  models/                  # SQLAlchemy-модели (client, master, service, appointment, ...)
  schemas/                 # Pydantic-схемы запросов/ответов (+ auth.py)
  api/                     # эндпоинты: health, auth, services, masters, slots, clients,
                           #            appointments, working_hours, webhook, deps
  patterns/
    repository/            # репозитории (Base + по сущностям), доступ к БД
    mapper/                # мапперы моделей
  services/
    slots.py               # расчёт свободных слотов
    status_machine.py      # граф переходов статусов записи
    booking_conflict.py    # проверка конфликта слотов / двойной записи
  bot/
    __main__.py            # точка входа бота (python -m app.bot)
    dispatcher.py          # сборка Bot + Dispatcher
    handlers.py            # обработчики сообщений/команд
    middlewares.py         # middleware (сессия БД на апдейт)
    states.py              # состояния FSM
    fsm.py                 # машина состояний диалога
    storage.py             # хранилища FSM (InMemory / Redis)
  migrations/              # миграции Alembic
tests/                     # тесты (pytest)
```

## Запуск тестов и линтера одной командой

```bash
uv run pytest -q && uv run ruff check .
```

## Оговорки текущего этапа

- Теста на сам exclusion-constraint (гонка на уровне БД) пока нет: он требует реального
  Postgres и отложен до интеграционных тестов.

Полный пошаговый план — в файле `salon-booking-plan.xlsx` (корень рабочей директории).
