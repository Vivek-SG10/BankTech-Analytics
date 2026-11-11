"""
Application configuration loaded from environment variables.
Copy .env.example → .env and fill in real values before starting.
"""
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
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
    gemini_api_key: str = ""
    openai_api_key: str = ""
    chroma_persist_directory: str = "./data/chroma_db"

    @property
    def effective_api_key(self) -> str:
        """Return GEMINI_API_KEY if set, otherwise fallback to OPENAI_API_KEY."""
        return self.gemini_api_key or self.openai_api_key

    @property
    def llm_provider(self) -> str:
        key = self.effective_api_key
        if self.gemini_api_key or key.startswith("AIza"):
            return "gemini"
        if self.openai_api_key or key.startswith("sk-"):
            return "openai"
        return "gemini" if key else "none"

    # RAG configuration
    rag_chunk_size: int = 800
    rag_chunk_overlap: int = 150
    rag_max_file_size_mb: int = 20
    rag_embed_model: str = "text-embedding-004"
    rag_generation_model: str = "gemini-2.0-flash"
    rag_max_distance: float = 1.5
    rag_request_timeout: int = 60

    # ── CORS ───────────────────────────────────────────────────────────────
    frontend_origin: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — safe to call anywhere."""
    return Settings()
