FROM python:3.13-slim

# uv — быстрый менеджер зависимостей. Копируем готовый бинарник из официального образа.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# PYTHONUNBUFFERED: логи сразу попадают в `docker compose logs`, а не копятся в буфере.
# UV_COMPILE_BYTECODE: компилируем .pyc заранее, приложение стартует быстрее.
# UV_LINK_MODE=copy: в контейнере копируем файлы, а не делаем ссылки на кэш.
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /srv

# Сначала только файлы зависимостей. Docker кэширует слои: пока pyproject.toml и uv.lock
# не изменились, зависимости не переустанавливаются при каждой правке кода.
# uv.lock* (со звёздочкой) значит «если файл есть». Когда он есть, uv ставит ровно те версии,
# что в нём записаны, и сборка воспроизводима. Как его создать, написано в README.
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --no-install-project

COPY app ./app
COPY alembic.ini ./

# Виртуальное окружение uv добавляем в PATH, чтобы вызывать `uvicorn` напрямую.
ENV PATH="/srv/.venv/bin:$PATH"

# Не запускаем приложение от root: при взломе у процесса будет меньше прав.
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]