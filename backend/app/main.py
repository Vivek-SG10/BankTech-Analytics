"""
BankTech Analytics — FastAPI application entry-point.

Phase 3: Survey submission + research analytics module added.
Phase 4: RAG-powered Knowledge Base (FAQ) module added.
Routers are imported at module level so startup errors are immediately visible.
Heavy optional dependencies (langchain, chromadb) remain guarded.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.auth.router import auth_router
from app.auth.seed import dev_router
from app.surveys.router import survey_router
from app.analytics.router import analytics_router
from app.core.config import get_settings

settings = get_settings()

# ── Optional Phase-3+ routers (RAG) ───────────────────────────────────────────
try:
    from app.api.router import api_router as _api_router  # type: ignore
    _api_router_available = True
except Exception:  # noqa: BLE001
    _api_router = None
    _api_router_available = False

try:
    from app.rag.router import rag_router as _rag_router
    _rag_router_available = True
except Exception:  # noqa: BLE001
    _rag_router = None
    _rag_router_available = False


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    # Ensure all tables (including rag_documents) exist on startup
    try:
        import logging
        from app.core.database import engine
        from app.auth.models import Base
        import app.surveys.models  # noqa: F401
        import app.rag.models      # noqa: F401
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Could not auto-create tables on startup: %s", e)
    yield
    from app.core.database import engine
    await engine.dispose()


app = FastAPI(
    title="BankTech Analytics API",
    description=(
        "Intelligent Banking Analytics and Financial Insights Platform.\n\n"
        "**Phase 3:** Survey submission, Technology Adoption Index, "
        "Employee Performance Index, Job Satisfaction Index, "
        "Customer Service Effectiveness Index, descriptive statistics, "
        "correlation and regression analyses.\n\n"
        "**Phase 4:** RAG-powered Knowledge Base FAQ — upload documents and "
        "query them with AI-generated, grounded answers."
    ),
    version="0.4.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_origin,
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Core routers ───────────────────────────────────────────────────────────────
app.include_router(health_router,    prefix="/api/v1")
app.include_router(auth_router,      prefix="/api/v1/auth",      tags=["Authentication"])
app.include_router(dev_router,       prefix="/api/v1/dev",       tags=["Development (dev-only)"])
app.include_router(survey_router,    prefix="/api/v1/surveys",   tags=["Surveys"])
app.include_router(analytics_router, prefix="/api/v1/analytics", tags=["Research Analytics"])

# ── Optional Phase-3+ routers ─────────────────────────────────────────────────
if _api_router_available and _api_router is not None:
    app.include_router(_api_router, prefix="/api/v1", tags=["Analytics & Core API"])
if _rag_router_available and _rag_router is not None:
    app.include_router(_rag_router, prefix="/api/v1/rag", tags=["Knowledge Base (RAG)"])
