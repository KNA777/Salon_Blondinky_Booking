# Salon Booking

Запись клиентов в салон красоты: FastAPI + Telegram-бот.

Сейчас готов **шаг 1**: каркас проекта (FastAPI, Postgres, Redis в Docker Compose) и эндпоинт `/health`.

## Запуск

```bash
cp .env.example .env        # затем поменяйте POSTGRES_PASSWORD
uv lock                     # один раз: зафиксировать версии зависимостей в uv.lock
docker compose up --build
```

`uv lock` создаёт файл `uv.lock` с точными версиями всех библиотек. Его нужно коммитить в git:
тогда у вас, у коллеги и на сервере ставятся одинаковые версии. Без него Docker тоже соберётся,
но версии будут «самые свежие на момент сборки».

Проверка:

- http://localhost:8000/health — должно вернуть `{"status":"ok","postgres":"ok","redis":"ok"}`
- http://localhost:8000/docs — автоматическая документация API

Остановить: `Ctrl+C`, затем `docker compose down` (данные БД сохранятся в томе `pgdata`;
чтобы удалить и их: `docker compose down -v`).

## Разработка без Docker (тесты и линтер)

Нужен [uv](https://docs.astral.sh/uv/).

```bash
uv sync               # создать .venv и поставить зависимости
uv run pytest         # тесты
uv run ruff check .   # линтер
uv run ruff format .  # форматирование
```

## Структура

```
app/
  main.py          # создание приложения, lifespan (старт/остановка)
  core/config.py   # настройки из переменных окружения
  api/deps.py      # зависимости FastAPI: сессия БД, Redis
  api/health.py    # эндпоинт /health
tests/
  test_health.py   # тесты /health с подменой зависимостей
```
