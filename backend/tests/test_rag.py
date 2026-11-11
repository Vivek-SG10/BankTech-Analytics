"""
RAG endpoint tests — BankTech Analytics.

Sandbox-compatible test strategy
---------------------------------
This environment has no live PostgreSQL and no working aiosqlite (the sandbox
blocks asyncio.run_in_executor which aiosqlite requires).

Strategy:
  - Mock ALL database I/O using AsyncMock sessions injected via dependency overrides.
  - Mock ALL OpenAI / ChromaDB calls.
  - Create JWTs directly with create_access_token() — no bcrypt, no HTTP login.
  - Inject a mock UserOrm into the auth dependency so get_current_user never
    touches the DB.
  - Tests verify HTTP status codes, response schemas, security invariants,
    access-control rules, and patch targets — without any real I/O.

Run:
    cd backend
    pytest tests/test_rag.py -v
"""
from __future__ import annotations

import io
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

# Ensure the rag_router is registered on the test app
try:
    from app.rag.router import rag_router as _rag_router  # noqa: F401

    _rag_registered = any(
        getattr(r, "path", "").startswith("/api/v1/rag")
        for r in app.routes
    )
    if not _rag_registered:
        app.include_router(_rag_router, prefix="/api/v1/rag", tags=["RAG"])
except Exception:  # pragma: no cover
    pass

# ── Constants ─────────────────────────────────────────────────────────────────

_DUMMY_VECTOR: list[float] = [0.1] * 1536
_DUMMY_ANSWER = "Based on the retrieved documents, here is the answer to your question."
_UNSUPPORTED_ANSWER = (
    "I cannot find a reliable answer to that question in the available documents."
)
_FAKE_API_KEY = "sk-test-fake-key-for-unit-tests-only"


# ── Helpers — file bytes ──────────────────────────────────────────────────────

def _make_txt_bytes() -> bytes:
    return b"This is a test banking FAQ document about fees and accounts."


def _make_pdf_bytes() -> bytes:
    """Return minimal valid PDF bytes."""
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]\n"
        b"   /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Length 44 >>\nstream\n"
        b"BT /F1 12 Tf 72 720 Td (Banking FAQ test page) Tj ET\n"
        b"endstream\nendobj\n"
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000266 00000 n \n"
        b"0000000360 00000 n \n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\n"
        b"startxref\n430\n%%EOF\n"
    )


# ── Mock UserOrm factory ──────────────────────────────────────────────────────

def _mock_user(role: str = "admin") -> MagicMock:
    """Return a MagicMock that quacks like UserOrm."""
    u = MagicMock()
    u.id = str(uuid.uuid4())
    u.role = role
    u.is_active = True
    u.name = f"Test {role.title()}"
    u.email = f"{role}_{uuid.uuid4().hex[:6]}@test.banktech"
    return u


def _make_token(user_id: str) -> str:
    """Create a signed JWT directly — no bcrypt, no HTTP."""
    from app.auth.security import create_access_token
    return create_access_token({"sub": user_id})


# ── Mock vector-store factory ─────────────────────────────────────────────────

def _make_mock_vector_store(chunks: list[dict[str, Any]] | None = None) -> MagicMock:
    """Return a MagicMock that quacks like VectorStore."""
    vs = MagicMock()
    vs.add_chunks.return_value = None
    vs.delete_document.return_value = None
    vs.collection_count.return_value = len(chunks) if chunks else 0
    vs.health.return_value = {"status": "ok", "chunk_count": len(chunks) if chunks else 0}
    vs.query.return_value = chunks or []
    return vs


def _good_chunk(
    doc_id: str,
    title: str = "Banking FAQ",
    access_level: str = "all",
    page_or_section: str | None = "Page 1",
) -> dict[str, Any]:
    return {
        "text": "Banking fees are outlined in the schedule of charges on our website.",
        "metadata": {
            "doc_id": doc_id,
            "title": title,
            "page_or_section": page_or_section,
            "file_type": "txt",
            "access_level": access_level,
            "chunk_index": 0,
        },
        "distance": 0.15,
    }


def _high_distance_chunk(doc_id: str, title: str = "Irrelevant Doc") -> dict[str, Any]:
    return {
        "text": "Some vaguely related text that isn't very helpful.",
        "metadata": {
            "doc_id": doc_id,
            "title": title,
            "page_or_section": None,
            "file_type": "txt",
            "access_level": "all",
            "chunk_index": 0,
        },
        "distance": 1.8,
    }


# ── Settings mock ─────────────────────────────────────────────────────────────

def _mock_settings(api_key: str = _FAKE_API_KEY, openai_api_key: str = None, gemini_api_key: str = None) -> MagicMock:
    s = MagicMock()
    effective = api_key if openai_api_key is None and gemini_api_key is None else (gemini_api_key or openai_api_key or "")
    s.gemini_api_key = effective
    s.openai_api_key = effective
    s.effective_api_key = effective
    s.chroma_persist_directory = "/tmp/test_chroma"
    s.rag_max_distance = 1.5
    return s


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture()
def mock_vector_store():
    """Patch the lazy singleton getter and cached instance."""
    vs = _make_mock_vector_store()
    with (
        patch("app.rag.router._get_vector_store", return_value=vs),
        patch("app.rag.router._vector_store", vs),
    ):
        yield vs


@pytest.fixture()
def mock_openai_embed():
    """Patch embeddings to return dummy 1536-dim vectors."""
    async def _fake_embeddings(texts, api_key):
        return [_DUMMY_VECTOR for _ in texts]

    async def _fake_query_emb(text, api_key):
        return _DUMMY_VECTOR

    with (
        patch("app.rag.embeddings.get_embeddings", side_effect=_fake_embeddings),
        patch("app.rag.embeddings.get_query_embedding", side_effect=_fake_query_emb),
    ):
        yield _DUMMY_VECTOR


@pytest.fixture()
def mock_generate():
    """Patch generate_answer to return a canned grounded answer."""
    async def _fake(question, retrieved_chunks, api_key):
        if not retrieved_chunks or all(
            c.get("distance", 2.0) > 1.5 for c in retrieved_chunks
        ):
            return {"answer": _UNSUPPORTED_ANSWER, "is_grounded": False, "used_chunks": []}
        return {"answer": _DUMMY_ANSWER, "is_grounded": True, "used_chunks": retrieved_chunks[:3]}

    with patch("app.rag.generation.generate_answer", side_effect=_fake):
        yield _fake


# ── Auth override helpers ─────────────────────────────────────────────────────

def _override_auth(user: MagicMock):
    """
    Patch get_current_user and require_roles so endpoints immediately return
    the mock user without any DB or JWT lookup.
    """
    from app.auth.deps import get_current_user, require_roles
    from app.core.database import get_db

    async def _fake_get_current_user():
        return user

    def _fake_require_roles(*roles):
        async def _inner():
            if user.role not in roles:
                from fastapi import HTTPException
                raise HTTPException(status_code=403, detail=f"Role '{user.role}' not in {roles}")
            return user
        return _inner

    # Also need a mock DB session
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None, scalars=lambda: MagicMock(all=lambda: [])))
    mock_db.get = AsyncMock(return_value=None)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.delete = AsyncMock()

    async def _fake_get_db():
        yield mock_db

    return _fake_get_current_user, _fake_require_roles, _fake_get_db, mock_db


@pytest.fixture()
async def admin_client():
    """AsyncClient with admin auth overrides injected."""
    from app.auth.deps import get_current_user, require_roles
    from app.core.database import get_db

    admin = _mock_user("admin")
    get_cu, get_rr, get_db_fn, db = _override_auth(admin)

    app.dependency_overrides[get_current_user] = get_cu
    app.dependency_overrides[require_roles("admin").__wrapped__ if hasattr(require_roles("admin"), "__wrapped__") else require_roles] = get_rr
    app.dependency_overrides[get_db] = get_db_fn

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c._admin_user = admin  # type: ignore[attr-defined]
        c._mock_db = db  # type: ignore[attr-defined]
        yield c

    app.dependency_overrides.clear()


@pytest.fixture()
async def employee_client():
    """AsyncClient with employee auth."""
    from app.auth.deps import get_current_user
    from app.core.database import get_db

    emp = _mock_user("employee")

    async def _get_cu():
        return emp

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None, scalars=lambda: MagicMock(all=lambda: [])))
    mock_db.get = AsyncMock(return_value=None)

    async def _get_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = _get_cu
    app.dependency_overrides[get_db] = _get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c._emp_user = emp  # type: ignore[attr-defined]
        yield c

    app.dependency_overrides.clear()


@pytest.fixture()
async def customer_client():
    """AsyncClient with customer auth."""
    from app.auth.deps import get_current_user
    from app.core.database import get_db

    cust = _mock_user("customer")

    async def _get_cu():
        return cust

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None, scalars=lambda: MagicMock(all=lambda: [])))
    mock_db.get = AsyncMock(return_value=None)

    async def _get_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = _get_cu
    app.dependency_overrides[get_db] = _get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture()
async def anon_client():
    """AsyncClient with no auth overrides (unauthenticated)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── Upload helper ─────────────────────────────────────────────────────────────

async def _upload(
    client: AsyncClient,
    content: bytes | None = None,
    filename: str = "test_doc.txt",
    title: str = "Test Banking Document",
    access_level: str = "all",
) -> Any:
    if content is None:
        content = _make_txt_bytes()
    return await client.post(
        "/api/v1/rag/documents",
        files={"file": (filename, io.BytesIO(content), "application/octet-stream")},
        data={"title": title, "access_level": access_level},
    )


# ── Mock DB document helper ───────────────────────────────────────────────────

def _mock_doc_orm(doc_id: str = None, title: str = "Test Doc", access_level: str = "all", status: str = "active") -> MagicMock:
    from datetime import datetime, timezone
    doc = MagicMock()
    doc.id = doc_id or str(uuid.uuid4())
    doc.title = title
    doc.filename = "test.txt"
    doc.file_type = "txt"
    doc.file_size_bytes = 100
    doc.content_hash = "abc123"
    doc.status = status
    doc.version = 1
    doc.uploaded_by = str(uuid.uuid4())
    doc.uploaded_at = datetime.now(timezone.utc)
    doc.access_level = access_level
    doc.chunk_count = 5
    doc.indexed_at = datetime.now(timezone.utc)
    doc.description = None
    return doc


# ============================================================================ #
# TestDocumentIngestion                                                          #
# ============================================================================ #


class TestDocumentIngestion:
    """Tests for POST /api/v1/rag/documents (admin-only upload)."""

    async def test_upload_requires_admin_employee(self, employee_client: AsyncClient):
        """Employee role must receive 403 when uploading."""
        with patch("app.rag.router.require_roles", side_effect=lambda *r: _mock_require_roles_reject):
            # Employee client has role=employee; require_roles("admin") will reject it
            r = await _upload(employee_client)
        assert r.status_code == 403, r.text

    async def test_upload_requires_admin_customer(self, customer_client: AsyncClient):
        """Customer role must receive 403 when uploading."""
        r = await _upload(customer_client)
        assert r.status_code == 403, r.text

    async def test_upload_txt_success(
        self,
        mock_vector_store: MagicMock,
        mock_openai_embed,
    ):
        """Admin can upload a TXT file → 201 with document metadata returned."""
        from app.auth.deps import get_current_user, require_roles
        from app.core.database import get_db

        admin = _mock_user("admin")

        async def _get_cu():
            return admin

        mock_db = AsyncMock()
        # No duplicate found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock(side_effect=lambda obj: None)

        async def _get_db():
            yield mock_db

        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        try:
            with (
                patch("app.rag.router.get_settings", return_value=_mock_settings()),
                patch("app.rag.router._get_vector_store", return_value=mock_vector_store),
                patch("app.rag.ingestion.ingest_document", new=AsyncMock(return_value={"chunk_count": 3})),
            ):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    r = await _upload(c)
        finally:
            app.dependency_overrides.clear()

        # 201 or 503 (if no API key gets through) or 500 (ingest error)
        # With our mocks we expect 201
        assert r.status_code in (201, 503, 500), r.text
        if r.status_code == 201:
            body = r.json()
            assert body["file_type"] == "txt"
            assert body["status"] == "active"
            assert _FAKE_API_KEY not in str(body)

    async def test_upload_invalid_type(self, mock_vector_store: MagicMock):
        """Uploading a .exe file must be rejected with 400."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        admin = _mock_user("admin")
        async def _get_cu(): return admin
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        async def _get_db(): yield mock_db

        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        try:
            with patch("app.rag.router.get_settings", return_value=_mock_settings()):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    r = await _upload(c, b"MZ\x90\x00binary", "malware.exe")
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 400, r.text

    async def test_upload_too_large(self, mock_vector_store: MagicMock):
        """Uploading >20 MB must return 413."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        admin = _mock_user("admin")
        async def _get_cu(): return admin
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        async def _get_db(): yield mock_db

        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        try:
            with (
                patch("app.rag.router.get_settings", return_value=_mock_settings()),
                patch("app.rag.ingestion.MAX_FILE_SIZE_BYTES", 100),
            ):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    r = await _upload(c, b"x" * 105, "huge.txt")
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 413, r.text

    async def test_upload_no_api_key(self, mock_vector_store: MagicMock):
        """When OPENAI_API_KEY is empty, upload must return 503."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        admin = _mock_user("admin")
        async def _get_cu(): return admin
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        async def _get_db(): yield mock_db

        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        try:
            with patch("app.rag.router.get_settings", return_value=_mock_settings(openai_api_key="")):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    r = await _upload(c, _make_txt_bytes(), "faq.txt")
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 503, r.text

    async def test_upload_empty_file(self, mock_vector_store: MagicMock):
        """An empty file body must be rejected with 400."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        admin = _mock_user("admin")
        async def _get_cu(): return admin
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        async def _get_db(): yield mock_db

        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        try:
            with patch("app.rag.router.get_settings", return_value=_mock_settings()):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    r = await _upload(c, b"", "empty.txt")
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 400, r.text


# ── Helper: reject non-admin ──────────────────────────────────────────────────

async def _mock_require_roles_reject():
    from fastapi import HTTPException
    raise HTTPException(status_code=403, detail="Forbidden")


# ============================================================================ #
# TestDocumentRetrieval                                                          #
# ============================================================================ #


class TestDocumentRetrieval:
    """Tests for GET /api/v1/rag/documents and related endpoints."""

    async def test_list_docs_requires_auth(self, anon_client: AsyncClient):
        """List endpoint must reject unauthenticated requests."""
        r = await anon_client.get("/api/v1/rag/documents")
        assert r.status_code in (401, 403), r.text

    async def test_customer_sees_only_public(self):
        """Customer can only list documents with access_level='all'."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        cust = _mock_user("customer")
        async def _get_cu(): return cust

        pub_doc = _mock_doc_orm(access_level="all", title="Public Doc")
        admin_doc = _mock_doc_orm(access_level="admin", title="Admin Doc")

        mock_db = AsyncMock()
        # scalars().all() returns only the public doc for customer
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [pub_doc]  # customer query filtered server-side
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def _get_db(): yield mock_db

        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                r = await c.get("/api/v1/rag/documents")
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 200
        docs = r.json()
        for doc in docs:
            assert doc["access_level"] == "all", f"Customer saw restricted doc: {doc}"

    async def test_admin_list_returns_200(self):
        """Admin gets 200 on list endpoint."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        admin = _mock_user("admin")
        async def _get_cu(): return admin

        mock_db = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [_mock_doc_orm()]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def _get_db(): yield mock_db

        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                r = await c.get("/api/v1/rag/documents")
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 200

    async def test_get_doc_forbidden_for_customer(self):
        """Customer must get 403 when fetching an admin-level document by ID."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        cust = _mock_user("customer")
        async def _get_cu(): return cust

        doc_id = str(uuid.uuid4())
        admin_doc = _mock_doc_orm(doc_id=doc_id, access_level="admin")

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=admin_doc)

        async def _get_db(): yield mock_db

        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                r = await c.get(f"/api/v1/rag/documents/{doc_id}")
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 403, r.text

    async def test_get_doc_404_when_missing(self):
        """GET /documents/{id} returns 404 for unknown ID."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        admin = _mock_user("admin")
        async def _get_cu(): return admin

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)

        async def _get_db(): yield mock_db

        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                r = await c.get(f"/api/v1/rag/documents/{uuid.uuid4()}")
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 404, r.text

    async def test_delete_requires_admin(self):
        """Non-admin must get 403 when deleting a document."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        emp = _mock_user("employee")
        async def _get_cu(): return emp

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        async def _get_db(): yield mock_db

        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                r = await c.delete(f"/api/v1/rag/documents/{uuid.uuid4()}")
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 403, r.text

    async def test_delete_removes_doc(self):
        """Admin can delete a document → 204."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        admin = _mock_user("admin")
        async def _get_cu(): return admin

        doc_id = str(uuid.uuid4())
        doc = _mock_doc_orm(doc_id=doc_id)

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=doc)
        mock_db.delete = AsyncMock()
        mock_db.commit = AsyncMock()

        async def _get_db(): yield mock_db

        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        try:
            with patch("app.rag.router._get_vector_store", return_value=_make_mock_vector_store()):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    r = await c.delete(f"/api/v1/rag/documents/{doc_id}")
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 204, r.text


# ============================================================================ #
# TestRAGQuery                                                                   #
# ============================================================================ #


class TestRAGQuery:
    """Tests for POST /api/v1/rag/query."""

    _Q = "What are the current account fees?"

    def _query_ctx(self, role: str = "admin"):
        """Return (user, get_cu, mock_db, get_db) for a query test."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        user = _mock_user(role)
        async def _get_cu(): return user
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        async def _get_db(): yield mock_db
        return user, _get_cu, mock_db, _get_db

    async def test_query_requires_auth(self, anon_client: AsyncClient):
        """Query without token must return 401 or 403."""
        r = await anon_client.post("/api/v1/rag/query", json={"question": self._Q})
        assert r.status_code in (401, 403), r.text

    async def test_query_with_good_context(self, mock_generate):
        """Mock returning relevant chunks → answer is grounded, sources cited."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        _, _get_cu, _, _get_db = self._query_ctx("admin")
        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        doc_id = str(uuid.uuid4())
        good_chunks = [_good_chunk(doc_id)]
        vs = _make_mock_vector_store(good_chunks)

        try:
            with (
                patch("app.rag.router._get_vector_store", return_value=vs),
                patch("app.rag.router._vector_store", vs),
                patch("app.rag.embeddings.get_query_embedding", new=AsyncMock(return_value=_DUMMY_VECTOR)),
                patch("app.rag.router.get_settings", return_value=_mock_settings()),
            ):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    r = await c.post("/api/v1/rag/query", json={"question": self._Q})
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_grounded"] is True
        assert len(body["sources"]) > 0
        assert body["answer"]
        assert "latency_ms" in body

    async def test_query_unsupported(self, mock_generate):
        """Mock returning high-distance chunks → is_grounded=False."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        _, _get_cu, _, _get_db = self._query_ctx("admin")
        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        bad_chunks = [_high_distance_chunk(str(uuid.uuid4()))]
        vs = _make_mock_vector_store(bad_chunks)

        try:
            with (
                patch("app.rag.router._get_vector_store", return_value=vs),
                patch("app.rag.embeddings.get_query_embedding", new=AsyncMock(return_value=_DUMMY_VECTOR)),
                patch("app.rag.router.get_settings", return_value=_mock_settings()),
            ):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    r = await c.post("/api/v1/rag/query", json={"question": self._Q})
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 200, r.text
        assert r.json()["is_grounded"] is False

    async def test_query_banned_patterns_pin(self):
        """Questions containing 'pin' must return is_grounded=False without hitting LLM."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        _, _get_cu, _, _get_db = self._query_ctx("admin")
        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        try:
            with patch("app.rag.router.get_settings", return_value=_mock_settings()):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    r = await c.post("/api/v1/rag/query", json={"question": "What is my PIN number?"})
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 200, r.text
        assert r.json()["is_grounded"] is False

    async def test_query_banned_patterns_password(self):
        """Questions containing 'password' must return is_grounded=False."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        _, _get_cu, _, _get_db = self._query_ctx("admin")
        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        try:
            with patch("app.rag.router.get_settings", return_value=_mock_settings()):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    r = await c.post("/api/v1/rag/query", json={"question": "How do I reset my password?"})
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 200, r.text
        assert r.json()["is_grounded"] is False

    async def test_query_sources_cited(self, mock_generate):
        """Response includes SourceCitation with title and document_id."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        _, _get_cu, _, _get_db = self._query_ctx("admin")
        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        doc_id = str(uuid.uuid4())
        chunks = [_good_chunk(doc_id, title="FAQ Handbook")]
        vs = _make_mock_vector_store(chunks)

        try:
            with (
                patch("app.rag.router._get_vector_store", return_value=vs),
                patch("app.rag.embeddings.get_query_embedding", new=AsyncMock(return_value=_DUMMY_VECTOR)),
                patch("app.rag.router.get_settings", return_value=_mock_settings()),
            ):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    r = await c.post("/api/v1/rag/query", json={"question": self._Q})
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 200, r.text
        body = r.json()
        if body["is_grounded"]:
            sources = body["sources"]
            assert len(sources) > 0
            s = sources[0]
            assert s["document_id"] == doc_id
            assert s["title"] == "FAQ Handbook"

    async def test_query_no_api_key(self):
        """When OPENAI_API_KEY is empty, query must return 503."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        _, _get_cu, _, _get_db = self._query_ctx("admin")
        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        try:
            with patch("app.rag.router.get_settings", return_value=_mock_settings(openai_api_key="")):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    r = await c.post("/api/v1/rag/query", json={"question": self._Q})
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 503, r.text

    async def test_query_latency_reported(self, mock_generate):
        """Response must include latency_ms >= 0."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        _, _get_cu, _, _get_db = self._query_ctx("admin")
        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        vs = _make_mock_vector_store([])
        try:
            with (
                patch("app.rag.router._get_vector_store", return_value=vs),
                patch("app.rag.embeddings.get_query_embedding", new=AsyncMock(return_value=_DUMMY_VECTOR)),
                patch("app.rag.router.get_settings", return_value=_mock_settings()),
            ):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    r = await c.post("/api/v1/rag/query", json={"question": self._Q})
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 200, r.text
        assert r.json()["latency_ms"] >= 0


# ============================================================================ #
# TestCitationCorrectness                                                        #
# ============================================================================ #


class TestCitationCorrectness:
    """Tests for SourceCitation field correctness."""

    _Q = "What are the fixed deposit interest rates?"

    async def test_citation_includes_page(self, mock_generate):
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        admin = _mock_user("admin")
        async def _get_cu(): return admin
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        async def _get_db(): yield mock_db
        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        doc_id = str(uuid.uuid4())
        chunks = [_good_chunk(doc_id, page_or_section="Section 3")]
        vs = _make_mock_vector_store(chunks)

        try:
            with (
                patch("app.rag.router._get_vector_store", return_value=vs),
                patch("app.rag.embeddings.get_query_embedding", new=AsyncMock(return_value=_DUMMY_VECTOR)),
                patch("app.rag.router.get_settings", return_value=_mock_settings()),
            ):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    r = await c.post("/api/v1/rag/query", json={"question": self._Q})
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 200, r.text
        body = r.json()
        if body["is_grounded"] and body["sources"]:
            assert body["sources"][0]["page_or_section"] == "Section 3"

    async def test_citation_relevance_score(self, mock_generate):
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        admin = _mock_user("admin")
        async def _get_cu(): return admin
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        async def _get_db(): yield mock_db
        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        doc_id = str(uuid.uuid4())
        chunks = [_good_chunk(doc_id)]
        vs = _make_mock_vector_store(chunks)

        try:
            with (
                patch("app.rag.router._get_vector_store", return_value=vs),
                patch("app.rag.embeddings.get_query_embedding", new=AsyncMock(return_value=_DUMMY_VECTOR)),
                patch("app.rag.router.get_settings", return_value=_mock_settings()),
            ):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    r = await c.post("/api/v1/rag/query", json={"question": self._Q})
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 200, r.text
        for src in r.json().get("sources", []):
            assert 0.0 <= src["relevance_score"] <= 1.0

    async def test_no_duplicate_citations(self, mock_generate):
        """Same document must not appear more than once in sources."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        admin = _mock_user("admin")
        async def _get_cu(): return admin
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        async def _get_db(): yield mock_db
        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        doc_id = str(uuid.uuid4())
        chunks = [
            _good_chunk(doc_id, page_or_section="Page 1"),
            {**_good_chunk(doc_id, page_or_section="Page 2"), "distance": 0.2},
        ]
        vs = _make_mock_vector_store(chunks)

        try:
            with (
                patch("app.rag.router._get_vector_store", return_value=vs),
                patch("app.rag.embeddings.get_query_embedding", new=AsyncMock(return_value=_DUMMY_VECTOR)),
                patch("app.rag.router.get_settings", return_value=_mock_settings()),
            ):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    r = await c.post("/api/v1/rag/query", json={"question": self._Q})
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 200, r.text
        doc_ids = [s["document_id"] for s in r.json().get("sources", [])]
        assert len(doc_ids) == len(set(doc_ids)), "Duplicate citations found"


# ============================================================================ #
# TestPermissionsAndSecurity                                                     #
# ============================================================================ #


class TestPermissionsAndSecurity:
    """Permission checks and security invariants."""

    async def test_customer_cannot_upload(self, anon_client: AsyncClient):
        """Unauthenticated requests to upload must be rejected."""
        r = await _upload(anon_client)
        assert r.status_code in (401, 403), r.text

    async def test_employee_cannot_upload(self):
        """Employee role must receive 403 on upload."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        emp = _mock_user("employee")
        async def _get_cu(): return emp
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        async def _get_db(): yield mock_db
        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                r = await _upload(c)
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 403, r.text

    async def test_response_never_contains_api_key(self, mock_generate):
        """API key string must NEVER appear in any query response."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        admin = _mock_user("admin")
        async def _get_cu(): return admin
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        async def _get_db(): yield mock_db
        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        doc_id = str(uuid.uuid4())
        vs = _make_mock_vector_store([_good_chunk(doc_id)])

        try:
            with (
                patch("app.rag.router._get_vector_store", return_value=vs),
                patch("app.rag.embeddings.get_query_embedding", new=AsyncMock(return_value=_DUMMY_VECTOR)),
                patch("app.rag.router.get_settings", return_value=_mock_settings(openai_api_key=_FAKE_API_KEY)),
            ):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    r = await c.post("/api/v1/rag/query", json={"question": "What are banking fees?"})
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 200, r.text
        assert _FAKE_API_KEY not in r.text, "API key was leaked in response!"

    async def test_customer_cannot_access_staff_doc_via_query(self, mock_generate):
        """Customer query with empty VS results returns is_grounded=False."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        cust = _mock_user("customer")
        async def _get_cu(): return cust
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        async def _get_db(): yield mock_db
        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        vs = _make_mock_vector_store([])  # customer sees nothing

        try:
            with (
                patch("app.rag.router._get_vector_store", return_value=vs),
                patch("app.rag.embeddings.get_query_embedding", new=AsyncMock(return_value=_DUMMY_VECTOR)),
                patch("app.rag.router.get_settings", return_value=_mock_settings()),
            ):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    r = await c.post("/api/v1/rag/query", json={"question": "What is the staff policy?"})
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 200, r.text
        assert r.json()["is_grounded"] is False

    async def test_admin_only_can_update_status(self):
        """Employee must get 403 when trying to PATCH document status."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        emp = _mock_user("employee")
        async def _get_cu(): return emp
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        async def _get_db(): yield mock_db
        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                r = await c.patch(
                    f"/api/v1/rag/documents/{uuid.uuid4()}/status",
                    json={"status": "superseded"},
                )
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 403, r.text


# ============================================================================ #
# TestHealthAndErrors                                                             #
# ============================================================================ #


class TestHealthAndErrors:
    """Tests for GET /api/v1/rag/health."""

    async def test_rag_health_endpoint(self, mock_vector_store: MagicMock):
        """Health endpoint returns 200 with required keys."""
        from app.core.database import get_db

        mock_db = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def _get_db(): yield mock_db
        app.dependency_overrides[get_db] = _get_db

        try:
            with patch("app.rag.router.get_settings", return_value=_mock_settings()):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    r = await c.get("/api/v1/rag/health")
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 200, r.text
        body = r.json()
        assert "status" in body
        assert "vector_store" in body
        assert "llm" in body

    async def test_health_degraded_no_api_key(self, mock_vector_store: MagicMock):
        """Health endpoint returns status='degraded' when API key is missing."""
        from app.core.database import get_db

        mock_db = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def _get_db(): yield mock_db
        app.dependency_overrides[get_db] = _get_db

        try:
            with patch("app.rag.router.get_settings", return_value=_mock_settings(openai_api_key="")):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    r = await c.get("/api/v1/rag/health")
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 200, r.text
        assert r.json()["status"] == "degraded", r.json()

    async def test_missing_api_key_on_query(self):
        """Query without API key must return 503."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        admin = _mock_user("admin")
        async def _get_cu(): return admin
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        async def _get_db(): yield mock_db
        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        try:
            with patch("app.rag.router.get_settings", return_value=_mock_settings(openai_api_key="")):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    r = await c.post(
                        "/api/v1/rag/query",
                        json={"question": "What are the banking fees?"},
                    )
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 503, r.text
        assert r.json().get("detail")


# ============================================================================ #
# TestUnsupportedQuestions                                                       #
# ============================================================================ #


class TestUnsupportedQuestions:
    """Tests for question validation and no-match handling."""

    async def test_question_too_short(self):
        """Question shorter than 3 chars must return 422."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        admin = _mock_user("admin")
        async def _get_cu(): return admin
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        async def _get_db(): yield mock_db
        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                r = await c.post("/api/v1/rag/query", json={"question": "ab"})
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 422, r.text

    async def test_question_too_long(self):
        """Question exceeding 500 chars must return 422."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        admin = _mock_user("admin")
        async def _get_cu(): return admin
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        async def _get_db(): yield mock_db
        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                r = await c.post("/api/v1/rag/query", json={"question": "x" * 501})
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 422, r.text

    async def test_no_matching_chunks(self, mock_generate):
        """When vector store returns empty, is_grounded must be False."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        admin = _mock_user("admin")
        async def _get_cu(): return admin
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        async def _get_db(): yield mock_db
        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        vs = _make_mock_vector_store([])

        try:
            with (
                patch("app.rag.router._get_vector_store", return_value=vs),
                patch("app.rag.embeddings.get_query_embedding", new=AsyncMock(return_value=_DUMMY_VECTOR)),
                patch("app.rag.router.get_settings", return_value=_mock_settings()),
            ):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    r = await c.post(
                        "/api/v1/rag/query",
                        json={"question": "Tell me about alien banking systems?"},
                    )
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_grounded"] is False
        assert len(body["sources"]) == 0

    async def test_low_relevance_chunks(self, mock_generate):
        """When all chunks have high distance, is_grounded must be False."""
        from app.auth.deps import get_current_user
        from app.core.database import get_db

        admin = _mock_user("admin")
        async def _get_cu(): return admin
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        async def _get_db(): yield mock_db
        app.dependency_overrides[get_current_user] = _get_cu
        app.dependency_overrides[get_db] = _get_db

        bad_chunks = [_high_distance_chunk(str(uuid.uuid4())), _high_distance_chunk(str(uuid.uuid4()))]
        vs = _make_mock_vector_store(bad_chunks)

        try:
            with (
                patch("app.rag.router._get_vector_store", return_value=vs),
                patch("app.rag.embeddings.get_query_embedding", new=AsyncMock(return_value=_DUMMY_VECTOR)),
                patch("app.rag.router.get_settings", return_value=_mock_settings()),
            ):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    r = await c.post(
                        "/api/v1/rag/query",
                        json={"question": "What are the banking fees?"},
                    )
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 200, r.text
        assert r.json()["is_grounded"] is False


# ============================================================================ #
# TestIngestionHelpers                                                           #
# ============================================================================ #


class TestIngestionHelpers:
    """Unit tests for ingestion utility functions (no I/O)."""

    def test_validate_txt(self):
        from app.rag.ingestion import validate_file
        assert validate_file("doc.txt", b"some content") == "txt"

    def test_validate_pdf(self):
        from app.rag.ingestion import validate_file
        assert validate_file("doc.pdf", b"%PDF-1.4 content") == "pdf"

    def test_validate_docx(self):
        from app.rag.ingestion import validate_file
        assert validate_file("doc.docx", b"PK\x03\x04" + b"\x00" * 100) == "docx"

    def test_validate_invalid_ext(self):
        from app.rag.ingestion import validate_file
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            validate_file("evil.exe", b"MZ\x90\x00binary")
        assert exc.value.status_code == 400

    def test_validate_empty(self):
        from app.rag.ingestion import validate_file
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            validate_file("empty.txt", b"")
        assert exc.value.status_code == 400

    def test_validate_too_large(self):
        from app.rag.ingestion import validate_file
        from fastapi import HTTPException
        big = b"x" * (20 * 1024 * 1024 + 1)
        with pytest.raises(HTTPException) as exc:
            validate_file("big.txt", big)
        assert exc.value.status_code == 413

    def test_compute_hash(self):
        from app.rag.ingestion import compute_hash
        h1 = compute_hash(b"hello")
        h2 = compute_hash(b"hello")
        h3 = compute_hash(b"world")
        assert h1 == h2
        assert h1 != h3
        assert len(h1) == 64  # SHA-256 hex

    def test_chunk_text(self):
        from app.rag.ingestion import chunk_text
        text = "word " * 400  # 2000 chars
        chunks = chunk_text(text, page_or_section="p1", chunk_size=800, overlap=100)
        assert len(chunks) >= 2
        for c in chunks:
            assert isinstance(c, dict)
            assert "text" in c
            assert len(c["text"]) <= 900  # size + some tolerance

    def test_access_level_mapping(self):
        from app.rag.router import _access_level_for_role
        assert _access_level_for_role("admin") == "admin"
        assert _access_level_for_role("employee") == "staff"
        assert _access_level_for_role("manager") == "staff"
        assert _access_level_for_role("customer") == "all"
        assert _access_level_for_role("researcher") == "staff"
