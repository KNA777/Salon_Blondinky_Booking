from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    """Все настройки приложения в одном месте.

    Значения берутся из переменных окружения (а при локальном запуске — ещё и из файла .env).
    Pydantic проверяет типы при старте: если обязательной переменной нет, приложение
    упадёт сразу с понятной ошибкой, а не в середине работы.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Обязательные: значений по умолчанию нет, пароль в коде хранить нельзя
    postgres_user: str
    postgres_password: str
    postgres_db: str

    postgres_host: str
    postgres_port: int

    redis_host: str
    redis_port: int

    # Часовой пояс салона. «Настенное» время в расписании относится к этому поясу.
    salon_timezone: str = "Europe/Moscow"

    # Токен Telegram-бота. Обязателен только для процесса бота, поэтому необязательный:
    # FastAPI стартует и без него. Бот при отсутствии токена падает с понятной ошибкой.
    bot_token: str | None = None

    # Webhook-режим. Если задан url, бот принимает апдейты через webhook (не polling).
    # Валидация входящих апдейтов — по секрету в заголовке X-Telegram-Bot-Api-Secret-Token.
    webhook_url: str | None = None
    # Секрет, которым Telegram подписывает webhook-запросы; сверяется с env-переменной.
    webhook_secret: str | None = None

    # --- JWT-аутентификация ---
    # Секретный ключ для подписи access-токенов. В продакшене обязателен и должен быть
    # длинной случайной строкой; для локальной разработки есть безопасный дефолт.
    jwt_secret_key: str = "dev-secret-change-me-in-production"
    # Алгоритм подписи (HS256 — симметричный, ключ один на подпись и проверку).
    jwt_algorithm: str = "HS256"
    # Время жизни access-токена, в минутах.
    jwt_expire_minutes: int = 60 * 24

    # --- Кука access_token (как JWT передаётся браузеру) ---
    # Имя cookie, в которой ходит access-токен. Браузер сам отсылает её на каждый запрос.
    cookie_name: str = "access_token"
    # HttpOnly всегда включён ниже в коде; Secure=True требует HTTPS, поэтому выключаем
    # для локальной разработки и включаем в продакшене (задать в .env).
    cookie_secure: bool = False
    # SameSite контролирует отправку куки на кросс-сайтовые запросы. Lax — безопасный
    # дефолт: кука идёт по переходам сверху, но не в чужих iframe/кросс-домен fetch.
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    # Путь действия куки — весь сайт по умолчанию.
    cookie_path: str = "/"

    # --- Безопасность эксплуатации ---
    # Название окружения: dev / prod. В prod включаются строгие проверки (см.
    # model_validator ниже): запрещено использовать dev-дефолтный JWT-ключ и открытые
    # (Secure=False) куки по HTTP.
    app_env: Literal["dev", "prod"] = "dev"

    # --- Напоминания о записи ---
    # За сколько времени до начала отправлять напоминания (в минутах).
    reminder_offsets_minutes: list[int] = [24 * 60, 2 * 60]
    # Как часто планировщик проверяет, кому пора слать напоминание (в секундах).
    reminder_poll_interval_seconds: int = 60

    # --- Наблюдаемость (задача 27) ---
    # DSN проекта в Sentry. Если не задан, Sentry не инициализируется и приложение
    # работает с обычным structlog-логированием.
    sentry_dsn: str | None = None
    # Доля трассировок, отправляемых в Sentry (0.0–1.0). В dev можно 0, в prod — 1.0
    # или меньше для экономии квоты.
    sentry_traces_sample_rate: float = 0.1

    @model_validator(mode="after")
    def _enforce_production_safety(self) -> "Settings":
        """Запрещает запуск продакшена с небезопасными настройками.

        В окружении prod:
        - JWT-ключ обязан быть заменён (иначе любой сможет подделать токен);
        - cookie обязана ходить только по HTTPS (Secure=True), иначе токен крадут на
          пути. Это «fail fast»: сервис не стартует в заведомо дырявой конфигурации,
          а падает с понятной ошибкой.
        """
        if self.app_env == "prod":
            if self.jwt_secret_key == "dev-secret-change-me-in-production":
                raise ValueError(
                    "В окружении prod задайте JWT_SECRET_KEY (длинную случайную строку) "
                    "и не оставляйте dev-дефолт."
                )
            if not self.cookie_secure:
                raise ValueError(
                    "В окружении prod задайте COOKIE_SECURE=true: access-токен должен "
                    "передаваться только по HTTPS."
                )
        return self

    @property
    def use_webhook(self) -> bool:
        """True, если бот настроен на webhook (задан webhook_url и токен есть)."""
        return bool(self.webhook_url and self.bot_token)

    @property
    def database_url(self) -> URL:
        # URL.create сам экранирует спецсимволы в пароле (@, :, / и т.д.).
        # Если собирать строку вручную через f-string, пароль с "@" сломает подключение.
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    # lru_cache: настройки читаются и проверяются один раз, а не при каждом запросе.
    # Обязательные поля (postgres_user и т.д.) заполняются из .env/переменных окружения,
    # чего mypy не видит — считает их «не переданными» аргументами конструктора.
    return Settings()  # type: ignore[call-arg]
