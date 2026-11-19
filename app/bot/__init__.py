"""Telegram-бот салона.

Бот — отдельный процесс (см. __main__.py), он не зависит от FastAPI: у него свой event
loop, и он сам открывает сессии БД через session_factory из app.state.
"""
