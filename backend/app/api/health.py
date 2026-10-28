"""
Health-check router.
GET /api/v1/health — returns API status and live database connectivity.
"""
import time
from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.database import ping_database

router = APIRouter()


@router.get(
    "/health",
    summary="System health check",
    response_description="API and database status",
    tags=["Health"],
)
async def health_check():
    """
    Returns HTTP 200 with the current health status.

    - **status**: always ``"ok"`` when this endpoint is reachable
    - **database**: ``"ok"`` if PostgreSQL responds, ``"unreachable"`` otherwise
    - **timestamp**: ISO-8601 UTC timestamp of the check
    """
    t0 = time.monotonic()
    db_ok = await ping_database()
    latency_ms = round((time.monotonic() - t0) * 1000, 1)

    return {
        "status": "ok",
        "service": "BankTech Analytics API",
        "database": "ok" if db_ok else "unreachable",
        "database_latency_ms": latency_ms if db_ok else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
