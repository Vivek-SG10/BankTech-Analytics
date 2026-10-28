"""
Application configuration loaded from environment variables.
Copy .env.example → .env and fill in real values before starting.
"""
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ────────────────────────────────────────────────────────────────
    app_name: str = "BankTech Analytics"
    environment: str = "development"
    port: int = 8000

    # ── Security ───────────────────────────────────────────────────────────
    secret_key: str = "change-me-before-production"
    access_token_expire_minutes: int = 60

    # ── Database ───────────────────────────────────────────────────────────
    # Driver: psycopg3 (psycopg[binary]) — pre-built wheels for Python 3.14.
    database_url: str = "postgresql+psycopg://banktech:banktechpass@localhost:5432/banktech_db"

    @field_validator("database_url")
    @classmethod
    def _patch_driver_scheme(cls, v: str) -> str:
        """
        Ensure DATABASE_URL uses the psycopg3 async prefix.
        Accepts plain postgresql://, postgresql+asyncpg://, or postgresql+psycopg://.
        """
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+psycopg://", 1)
        if v.startswith("postgresql+asyncpg://"):
            return v.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
        return v

    # ── (Phase 1+) LLM / RAG ──────────────────────────────────────────────
    openai_api_key: str = ""
    chroma_persist_directory: str = "./data/chroma_db"

    # ── CORS ───────────────────────────────────────────────────────────────
    frontend_origin: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — safe to call anywhere."""
    return Settings()
