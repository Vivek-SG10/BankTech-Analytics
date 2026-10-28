"""
Async database engine and session management.
Driver: psycopg3 (psycopg[binary]) — pre-built wheels, no compiler needed.
SQLAlchemy URL scheme: postgresql+psycopg://
"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.sql import text

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.environment == "development",
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db():
    """Dependency: yields a database session and closes it afterwards."""
    async with AsyncSessionLocal() as session:
        yield session


async def ping_database() -> bool:
    """
    Attempt a lightweight query against the database.
    Returns True if the database responds, False otherwise.
    Does NOT raise — callers decide how to surface failures.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False
