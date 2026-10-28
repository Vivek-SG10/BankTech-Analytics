"""
Alembic environment for BankTech Analytics.

• Async mode (run_async_migrations) using SQLAlchemy asyncio engine.
• DATABASE_URL is read from the environment (or .env) — the alembic.ini
  value is used only as a fallback for local dev without Docker.
• target_metadata is set from the project's ORM Base so autogenerate works.
"""
from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# ── Load our ORM Base so Alembic can diff the schema ─────────────────────────
# All ORM models must be imported (directly or transitively) before autogenerate.
from app.auth.models import Base  # noqa: F401 — registers UserOrm with metadata
import app.surveys.models  # noqa: F401 — registers survey tables with the shared Base


# ── Alembic config ────────────────────────────────────────────────────────────
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# ── DB URL — env var takes precedence over alembic.ini ───────────────────────
# Load .env so `alembic upgrade head` works without pre-exporting env vars.
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    load_dotenv(os.path.abspath(_env_path), override=False)
except ImportError:
    pass  # python-dotenv not installed — rely on shell env vars


def get_url() -> str:
    url = os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url", "")
    # Normalise to psycopg3 async scheme
    for old, new in (
        ("postgresql://", "postgresql+psycopg://"),
        ("postgresql+asyncpg://", "postgresql+psycopg://"),
    ):
        if url.startswith(old):
            url = url.replace(old, new, 1)
            break
    return url


# ── Offline migrations (generate SQL without a live DB) ──────────────────────
def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online migrations (connect and apply) ─────────────────────────────────────
def do_run_migrations(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(get_url())
    async with engine.connect() as conn:
        await conn.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    import selectors
    import sys

    # psycopg3 async is incompatible with Windows ProactorEventLoop.
    # Force SelectorEventLoop when running on Windows.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()  # type: ignore[attr-defined]
        )
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
