"""
Phase-0 backend health tests.

Run with:
    cd backend
    pytest tests/test_health.py -v
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_health_endpoint_returns_200():
    """The health endpoint must always return HTTP 200."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_health_response_schema():
    """The response must contain the required fields with correct types."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "BankTech Analytics API"
    assert body["database"] in ("ok", "unreachable")
    assert "timestamp" in body


@pytest.mark.anyio
async def test_health_content_type_is_json():
    """The response Content-Type must be application/json."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert "application/json" in response.headers["content-type"]
