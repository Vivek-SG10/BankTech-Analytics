"""
Auth endpoint integration tests — Phase 2.

Uses in-memory SQLite (aiosqlite) so no live Postgres is required.
FastAPI dependency overrides swap get_db for the test session.

Run:
    cd backend
    pytest tests/test_auth.py -v
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.models import Base
from app.core.database import get_db
from app.main import app

# ── Test DB ───────────────────────────────────────────────────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
_SessionLocal = async_sessionmaker(bind=_engine, expire_on_commit=False, class_=AsyncSession)


@pytest.fixture(autouse=True)
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def setup_db():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture()
async def client():
    async def override_get_db():
        async with _SessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# ── Fixtures ──────────────────────────────────────────────────────────────────

EMPLOYEE = {"name": "Alice", "email": "alice@ex.com", "password": "SecurePass1!", "role": "employee"}
MANAGER  = {"name": "Bob",   "email": "bob@ex.com",   "password": "SecurePass1!", "role": "manager"}
CUSTOMER = {"name": "Carol", "email": "carol@ex.com", "password": "SecurePass1!", "role": "customer"}


async def _register(client: AsyncClient, payload: dict) -> dict:
    r = await client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


async def _login(client: AsyncClient, email: str, password: str) -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── 1. Registration ───────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_register_employee_success(client: AsyncClient):
    body = await _register(client, EMPLOYEE)
    assert body["user"]["role"] == "employee"
    assert body["user"]["email"] == EMPLOYEE["email"]
    assert "hashed_password" not in body["user"]
    assert "access_token" in body


@pytest.mark.anyio
async def test_register_all_allowed_roles(client: AsyncClient):
    for role in ("employee", "manager", "customer"):
        r = await client.post("/api/v1/auth/register", json={
            **EMPLOYEE, "email": f"{role}@ex.com", "role": role,
        })
        assert r.status_code == 201, f"role={role} failed: {r.text}"


@pytest.mark.anyio
async def test_register_admin_role_blocked(client: AsyncClient):
    """Clients must not self-assign admin or researcher."""
    for role in ("admin", "researcher"):
        r = await client.post("/api/v1/auth/register", json={
            **EMPLOYEE, "email": f"{role}@ex.com", "role": role,
        })
        assert r.status_code == 422, f"Expected 422 for role={role}, got {r.status_code}"


@pytest.mark.anyio
async def test_register_duplicate_email(client: AsyncClient):
    await _register(client, EMPLOYEE)
    r = await client.post("/api/v1/auth/register", json=EMPLOYEE)
    assert r.status_code == 409


@pytest.mark.anyio
async def test_register_short_password(client: AsyncClient):
    r = await client.post("/api/v1/auth/register", json={**EMPLOYEE, "password": "short"})
    assert r.status_code == 422


@pytest.mark.anyio
async def test_register_invalid_email(client: AsyncClient):
    r = await client.post("/api/v1/auth/register", json={**EMPLOYEE, "email": "not-an-email"})
    assert r.status_code == 422


# ── 2. Password hashing ───────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_password_never_returned(client: AsyncClient):
    """Hashed password must never appear in any response."""
    body = await _register(client, EMPLOYEE)
    assert "hashed_password" not in str(body)
    assert "password" not in str(body["user"])


# ── 3. Login ──────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_login_success(client: AsyncClient):
    await _register(client, EMPLOYEE)
    r = await client.post("/api/v1/auth/login", json={"email": EMPLOYEE["email"], "password": EMPLOYEE["password"]})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == EMPLOYEE["email"]


@pytest.mark.anyio
async def test_login_wrong_password(client: AsyncClient):
    await _register(client, EMPLOYEE)
    r = await client.post("/api/v1/auth/login", json={"email": EMPLOYEE["email"], "password": "wrong!"})
    assert r.status_code == 401


@pytest.mark.anyio
async def test_login_unknown_email(client: AsyncClient):
    r = await client.post("/api/v1/auth/login", json={"email": "nobody@ex.com", "password": "whatever"})
    assert r.status_code == 401


@pytest.mark.anyio
async def test_login_same_error_for_wrong_email_and_password(client: AsyncClient):
    """Both wrong-email and wrong-password return identical 401 detail to prevent enumeration."""
    await _register(client, EMPLOYEE)
    r1 = await client.post("/api/v1/auth/login", json={"email": "nobody@ex.com", "password": "x"})
    r2 = await client.post("/api/v1/auth/login", json={"email": EMPLOYEE["email"], "password": "x"})
    assert r1.json()["detail"] == r2.json()["detail"]


# ── 4. GET /me ────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_me_valid_token(client: AsyncClient):
    await _register(client, EMPLOYEE)
    token = await _login(client, EMPLOYEE["email"], EMPLOYEE["password"])
    r = await client.get("/api/v1/auth/me", headers=await _auth(token))
    assert r.status_code == 200
    assert r.json()["email"] == EMPLOYEE["email"]


@pytest.mark.anyio
async def test_me_no_token(client: AsyncClient):
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 403  # HTTPBearer raises 403 when header missing


@pytest.mark.anyio
async def test_me_invalid_token(client: AsyncClient):
    r = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


# ── 5. Logout ─────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_logout_returns_204(client: AsyncClient):
    r = await client.post("/api/v1/auth/logout")
    assert r.status_code == 204
    assert r.content == b""


# ── 6. Role-based access control ──────────────────────────────────────────────

@pytest.mark.anyio
async def test_employee_cannot_list_users(client: AsyncClient):
    await _register(client, EMPLOYEE)
    token = await _login(client, EMPLOYEE["email"], EMPLOYEE["password"])
    r = await client.get("/api/v1/auth/users", headers=await _auth(token))
    assert r.status_code == 403


@pytest.mark.anyio
async def test_customer_cannot_list_users(client: AsyncClient):
    await _register(client, CUSTOMER)
    token = await _login(client, CUSTOMER["email"], CUSTOMER["password"])
    r = await client.get("/api/v1/auth/users", headers=await _auth(token))
    assert r.status_code == 403


@pytest.mark.anyio
async def test_manager_cannot_list_users(client: AsyncClient):
    await _register(client, MANAGER)
    token = await _login(client, MANAGER["email"], MANAGER["password"])
    r = await client.get("/api/v1/auth/users", headers=await _auth(token))
    assert r.status_code == 403


# ── 7. Admin role assignment ──────────────────────────────────────────────────

@pytest.mark.anyio
async def test_seed_creates_demo_accounts(client: AsyncClient):
    r = await client.post("/api/v1/dev/seed")
    assert r.status_code == 200
    roles = {u["role"] for u in r.json()}
    assert roles == {"admin", "researcher", "manager", "employee", "customer"}


@pytest.mark.anyio
async def test_admin_can_list_users(client: AsyncClient):
    await client.post("/api/v1/dev/seed")
    token = await _login(client, "admin@banktech.dev", "Demo1234!")
    r = await client.get("/api/v1/auth/users", headers=await _auth(token))
    assert r.status_code == 200
    assert len(r.json()) >= 5


@pytest.mark.anyio
async def test_admin_can_set_role(client: AsyncClient):
    """Admin can promote a customer to researcher."""
    await client.post("/api/v1/dev/seed")
    admin_token = await _login(client, "admin@banktech.dev", "Demo1234!")

    # Register a new customer
    reg = await _register(client, CUSTOMER)
    uid = reg["user"]["id"]
    assert reg["user"]["role"] == "customer"

    # Admin promotes to researcher
    r = await client.patch(
        f"/api/v1/auth/users/{uid}/role",
        json={"role": "researcher"},
        headers=await _auth(admin_token),
    )
    assert r.status_code == 200
    assert r.json()["role"] == "researcher"


@pytest.mark.anyio
async def test_admin_cannot_change_own_role(client: AsyncClient):
    await client.post("/api/v1/dev/seed")
    admin_token = await _login(client, "admin@banktech.dev", "Demo1234!")
    me = await client.get("/api/v1/auth/me", headers=await _auth(admin_token))
    admin_id = me.json()["id"]
    r = await client.patch(
        f"/api/v1/auth/users/{admin_id}/role",
        json={"role": "customer"},
        headers=await _auth(admin_token),
    )
    assert r.status_code == 400


@pytest.mark.anyio
async def test_employee_cannot_change_roles(client: AsyncClient):
    await _register(client, EMPLOYEE)
    await _register(client, CUSTOMER)
    emp_token = await _login(client, EMPLOYEE["email"], EMPLOYEE["password"])

    # Get the customer's id via login
    cust_resp = await _register(client, {**CUSTOMER, "email": "carol2@ex.com"})
    cust_id = cust_resp["user"]["id"]

    r = await client.patch(
        f"/api/v1/auth/users/{cust_id}/role",
        json={"role": "admin"},
        headers=await _auth(emp_token),
    )
    assert r.status_code == 403


@pytest.mark.anyio
async def test_seed_is_idempotent(client: AsyncClient):
    r1 = await client.post("/api/v1/dev/seed")
    r2 = await client.post("/api/v1/dev/seed")
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Second call returns empty list (all already exist)
    assert r2.json() == []
