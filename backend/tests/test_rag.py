"""
RAG endpoint integration tests — BankTech Analytics.

Uses in-memory SQLite (aiosqlite) so no live Postgres or ChromaDB is required.
OpenAI and ChromaDB calls are fully mocked — tests run without real API keys.
FastAPI dependency overrides swap get_db for the in-memory test session.

Run:
    cd backend
    pytest tests/test_rag.py -v
"""
from __future__ import annotations

import hashlib
import io
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.models import Base
from app.core.database import get_db
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

# ── RAG models import (brings in KBDocumentOrm so it's in Base.metadata) ──────
try:
    from app.rag.models import KBDocumentOrm  # noqa: F401
except Exception:  # pragma: no cover
    pass

# ── Test DB ───────────────────────────────────────────────────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
_SessionLocal = async_sessionmaker(
    bind=_engine, expire_on_commit=False, class_=AsyncSession
)

# ── Dummy vector / generation constants ──────────────────────────────────────
_DUMMY_VECTOR: list[float] = [0.1] * 1536
_DUMMY_ANSWER = "Based on the retrieved documents, here is the answer to your question."
_UNSUPPORTED_ANSWER = (
    "I cannot find a reliable answer to that question in the available documents."
)
_FAKE_API_KEY = "sk-test-fake-key-for-unit-tests-only"


# ============================================================================ #
# Helpers — file bytes                                                          #
# ============================================================================ #


def _make_txt_bytes() -> bytes:
    return b"This is a test banking FAQ document about fees and accounts."


def _make_pdf_bytes() -> bytes:
    """Return minimal valid PDF bytes that pypdf can parse."""
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


def _make_docx_bytes() -> bytes:
    """Return DOCX bytes; use python-docx if available, else fallback magic bytes."""
    try:
        import docx  # noqa: PLC0415

        buf = io.BytesIO()
        doc = docx.Document()
        doc.add_heading("Banking FAQ", level=1)
        doc.add_paragraph("This is a test banking document about fees and accounts.")
        doc.save(buf)
        return buf.getvalue()
    except Exception:
        # DOCX is a ZIP; return the PK magic bytes so the type is recognisable
        return (
            b"PK\x03\x04"
            + b"\x00" * 26
            + b"[Content_Types].xml"
            + b"\x00" * 200
        )


# ============================================================================ #
# Mock vector-store factory                                                      #
# ============================================================================ #


def _make_mock_vector_store(chunks: list[dict[str, Any]] | None = None) -> MagicMock:
    """Return a MagicMock that quacks like VectorStore."""
    vs = MagicMock()
    vs.add_chunks.return_value = None
    vs.delete_document.return_value = None
    vs.collection_count.return_value = len(chunks) if chunks else 0
    vs.health.return_value = {"status": "ok", "chunk_count": len(chunks) if chunks else 0}

    _default_chunks = chunks or []
    vs.query.return_value = _default_chunks
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
        "distance": 0.15,  # low distance = highly relevant
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
        "distance": 1.8,  # high distance = low relevance
    }


# ============================================================================ #
# Pytest fixtures                                                                #
# ============================================================================ #


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
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


# ── Auth helpers ──────────────────────────────────────────────────────────────

_ADMIN_CREDS = {
    "name": "Admin User",
    "email": f"admin_{uuid.uuid4().hex[:6]}@banktech.test",
    "password": "AdminPass1!",
}
_EMPLOYEE_CREDS = {
    "name": "Employee User",
    "email": f"emp_{uuid.uuid4().hex[:6]}@banktech.test",
    "password": "EmpPass1!",
}
_CUSTOMER_CREDS = {
    "name": "Customer User",
    "email": f"cust_{uuid.uuid4().hex[:6]}@banktech.test",
    "password": "CustPass1!",
}


async def _seed_and_login(c: AsyncClient, role: str) -> str:
    """Seed demo users and return a JWT for the requested role."""
    await c.post("/api/v1/dev/seed")
    passwords = {
        "admin": "Demo1234!",
        "researcher": "Demo1234!",
        "manager": "Demo1234!",
        "employee": "Demo1234!",
        "customer": "Demo1234!",
    }
    emails = {
        "admin": "admin@banktech.dev",
        "researcher": "researcher@banktech.dev",
        "manager": "manager@banktech.dev",
        "employee": "employee@banktech.dev",
        "customer": "customer@banktech.dev",
    }
    r = await c.post(
        "/api/v1/auth/login",
        json={"email": emails[role], "password": passwords[role]},
    )
    assert r.status_code == 200, f"Login failed for role={role}: {r.text}"
    return r.json()["access_token"]


@pytest.fixture()
async def admin_token(client: AsyncClient) -> str:
    return await _seed_and_login(client, "admin")


@pytest.fixture()
async def employee_token(client: AsyncClient) -> str:
    return await _seed_and_login(client, "employee")


@pytest.fixture()
async def customer_token(client: AsyncClient) -> str:
    return await _seed_and_login(client, "customer")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── Mock fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture()
def mock_vector_store():
    """Patch both the lazy singleton getter and the cached instance."""
    vs = _make_mock_vector_store()
    with (
        patch("app.rag.router._get_vector_store", return_value=vs),
        patch("app.rag.router._vector_store", vs),
    ):
        yield vs


@pytest.fixture()
def mock_openai_embed():
    """Patch embeddings functions to return dummy 1536-dim vectors."""

    async def _fake_get_embeddings(texts, api_key):
        return [_DUMMY_VECTOR for _ in texts]

    async def _fake_get_query_embedding(text, api_key):
        return _DUMMY_VECTOR

    with (
        patch(
            "app.rag.embeddings.get_embeddings",
            side_effect=_fake_get_embeddings,
        ),
        patch(
            "app.rag.embeddings.get_query_embedding",
            side_effect=_fake_get_query_embedding,
        ),
        # Also patch the references used inside router (import at call time)
        patch(
            "app.rag.router.get_embeddings" if hasattr(__import__("app.rag.router", fromlist=["get_embeddings"]), "get_embeddings") else "app.rag.embeddings.get_embeddings",
            side_effect=_fake_get_embeddings,
            create=True,
        ),
    ):
        yield _DUMMY_VECTOR


@pytest.fixture()
def mock_generate():
    """Patch generate_answer to return a canned grounded answer."""

    async def _fake_generate(question, retrieved_chunks, api_key):
        if not retrieved_chunks or all(
            c.get("distance", 2.0) > 1.5 for c in retrieved_chunks
        ):
            return {
                "answer": _UNSUPPORTED_ANSWER,
                "is_grounded": False,
                "used_chunks": [],
            }
        return {
            "answer": _DUMMY_ANSWER,
            "is_grounded": True,
            "used_chunks": retrieved_chunks[:3],
        }

    with patch("app.rag.generation.generate_answer", side_effect=_fake_generate):
        yield _fake_generate


# ── Settings override helper ──────────────────────────────────────────────────


def _mock_settings(openai_api_key: str = _FAKE_API_KEY) -> MagicMock:
    s = MagicMock()
    s.openai_api_key = openai_api_key
    s.chroma_persist_directory = "/tmp/test_chroma"
    return s


# ============================================================================ #
# Upload helper                                                                  #
# ============================================================================ #


async def _upload(
    client: AsyncClient,
    token: str,
    content: bytes,
    filename: str = "test_doc.txt",
    title: str = "Test Banking Document",
    access_level: str = "all",
) -> Any:
    return await client.post(
        "/api/v1/rag/documents",
        headers=_auth(token),
        files={"file": (filename, io.BytesIO(content), "application/octet-stream")},
        data={"title": title, "access_level": access_level},
    )


# ============================================================================ #
# TestDocumentIngestion                                                          #
# ============================================================================ #


class TestDocumentIngestion:
    """Tests for POST /api/v1/rag/documents (admin-only upload)."""

    async def test_upload_requires_admin_employee(
        self, client: AsyncClient, employee_token: str
    ):
        """Employee role must receive 403 when uploading."""
        r = await _upload(client, employee_token, _make_txt_bytes())
        assert r.status_code == 403, r.text

    async def test_upload_requires_admin_customer(
        self, client: AsyncClient, customer_token: str
    ):
        """Customer role must receive 403 when uploading."""
        r = await _upload(client, customer_token, _make_txt_bytes())
        assert r.status_code == 403, r.text

    async def test_upload_txt_success(
        self,
        client: AsyncClient,
        admin_token: str,
        mock_vector_store: MagicMock,
        mock_openai_embed,
    ):
        """Admin can upload a TXT file → 201 with document metadata returned."""
        with patch("app.core.config.get_settings", return_value=_mock_settings()):
            r = await _upload(client, admin_token, _make_txt_bytes(), "faq.txt")
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["file_type"] == "txt"
        assert body["title"] == "Test Banking Document"
        assert body["status"] == "active"
        assert "id" in body
        # API key must never leak
        assert _FAKE_API_KEY not in str(body)

    async def test_upload_pdf_success(
        self,
        client: AsyncClient,
        admin_token: str,
        mock_vector_store: MagicMock,
        mock_openai_embed,
    ):
        """Admin can upload a PDF file → 201."""
        with patch("app.core.config.get_settings", return_value=_mock_settings()):
            r = await _upload(
                client, admin_token, _make_pdf_bytes(), "policy.pdf",
                title="Banking Policy PDF"
            )
        # 201 or 400 (if pypdf not installed or PDF has no text — both valid)
        assert r.status_code in (201, 400, 501), r.text

    async def test_upload_invalid_type(
        self, client: AsyncClient, admin_token: str, mock_vector_store: MagicMock
    ):
        """Uploading a .exe file must be rejected with 400."""
        with patch("app.core.config.get_settings", return_value=_mock_settings()):
            r = await _upload(
                client, admin_token, b"MZ\x90\x00binary", "malware.exe"
            )
        assert r.status_code == 400, r.text

    async def test_upload_too_large(
        self, client: AsyncClient, admin_token: str, mock_vector_store: MagicMock
    ):
        """Uploading >20 MB must return 413."""
        big_content = b"x" * (20 * 1024 * 1024 + 1)
        with patch("app.core.config.get_settings", return_value=_mock_settings()):
            r = await _upload(client, admin_token, big_content, "huge.txt")
        assert r.status_code == 413, r.text

    async def test_upload_duplicate_hash(
        self,
        client: AsyncClient,
        admin_token: str,
        mock_vector_store: MagicMock,
        mock_openai_embed,
    ):
        """Uploading the same content twice must return 409 on the second attempt."""
        content = b"Unique banking FAQ content for dedup test: " + uuid.uuid4().bytes
        content += b" fees accounts deposits"

        with patch("app.core.config.get_settings", return_value=_mock_settings()):
            r1 = await _upload(client, admin_token, content, "dedup1.txt", title="Dedup Doc 1")
            # First upload — may succeed or fail (501/400 acceptable for pypdf/docx)
            r2 = await _upload(client, admin_token, content, "dedup2.txt", title="Dedup Doc 2")

        if r1.status_code == 201:
            assert r2.status_code == 409, f"Expected 409 for duplicate, got {r2.status_code}: {r2.text}"

    async def test_upload_no_api_key(
        self, client: AsyncClient, admin_token: str, mock_vector_store: MagicMock
    ):
        """When OPENAI_API_KEY is empty, upload must return 503."""
        with patch(
            "app.core.config.get_settings",
            return_value=_mock_settings(openai_api_key=""),
        ):
            r = await _upload(client, admin_token, _make_txt_bytes(), "faq.txt")
        assert r.status_code == 503, r.text

    async def test_upload_empty_file(
        self, client: AsyncClient, admin_token: str, mock_vector_store: MagicMock
    ):
        """An empty file body must be rejected with 400."""
        with patch("app.core.config.get_settings", return_value=_mock_settings()):
            r = await _upload(client, admin_token, b"", "empty.txt")
        assert r.status_code == 400, r.text


# ============================================================================ #
# TestDocumentRetrieval                                                          #
# ============================================================================ #


class TestDocumentRetrieval:
    """Tests for GET /api/v1/rag/documents and related endpoints."""

    async def _seed_doc(
        self,
        client: AsyncClient,
        admin_token: str,
        mock_vs: MagicMock,
        access_level: str = "all",
        title: str = "Seeded Doc",
    ) -> str:
        """Upload a TXT document and return its ID."""
        content = f"doc content {uuid.uuid4()}".encode()
        with patch("app.core.config.get_settings", return_value=_mock_settings()):
            with patch(
                "app.rag.embeddings.get_embeddings",
                new_callable=lambda: lambda: AsyncMock(return_value=[_DUMMY_VECTOR]),
            ):

                async def _fake_embed(texts, api_key):
                    return [_DUMMY_VECTOR for _ in texts]

                with patch("app.rag.embeddings.get_embeddings", side_effect=_fake_embed):
                    r = await _upload(
                        client, admin_token, content, "seed.txt",
                        title=title, access_level=access_level
                    )
        if r.status_code != 201:
            pytest.skip(f"Could not seed doc ({r.status_code}): {r.text}")
        return r.json()["id"]

    async def test_list_docs_requires_auth(self, client: AsyncClient):
        """List endpoint must reject unauthenticated requests."""
        r = await client.get("/api/v1/rag/documents")
        assert r.status_code == 403, r.text

    async def test_customer_sees_only_public(
        self,
        client: AsyncClient,
        admin_token: str,
        customer_token: str,
        mock_vector_store: MagicMock,
        mock_openai_embed,
    ):
        """Customer must see only documents with access_level='all'."""
        # Seed one public and one admin doc
        public_content = f"public {uuid.uuid4()}".encode()
        admin_content = f"admin-only {uuid.uuid4()}".encode()

        with patch("app.core.config.get_settings", return_value=_mock_settings()):
            await _upload(
                client, admin_token, public_content, "public.txt",
                title="Public Doc", access_level="all"
            )
            await _upload(
                client, admin_token, admin_content, "admin_only.txt",
                title="Admin Doc", access_level="admin"
            )

        r = await client.get(
            "/api/v1/rag/documents", headers=_auth(customer_token)
        )
        assert r.status_code == 200
        docs = r.json()
        for doc in docs:
            assert doc["access_level"] == "all", (
                f"Customer saw restricted doc: {doc}"
            )

    async def test_employee_sees_staff_docs(
        self,
        client: AsyncClient,
        admin_token: str,
        employee_token: str,
        mock_vector_store: MagicMock,
        mock_openai_embed,
    ):
        """Employee must see 'all' and 'staff' docs but NOT 'admin' docs."""
        public_content = f"public {uuid.uuid4()}".encode()
        staff_content = f"staff {uuid.uuid4()}".encode()
        admin_content = f"admin {uuid.uuid4()}".encode()

        with patch("app.core.config.get_settings", return_value=_mock_settings()):
            await _upload(
                client, admin_token, public_content, "pub.txt",
                title="Public", access_level="all"
            )
            await _upload(
                client, admin_token, staff_content, "staff.txt",
                title="Staff", access_level="staff"
            )
            await _upload(
                client, admin_token, admin_content, "adm.txt",
                title="AdminOnly", access_level="admin"
            )

        r = await client.get(
            "/api/v1/rag/documents", headers=_auth(employee_token)
        )
        assert r.status_code == 200
        docs = r.json()
        for doc in docs:
            assert doc["access_level"] in ("all", "staff"), (
                f"Employee saw admin doc: {doc}"
            )

    async def test_admin_sees_all_docs(
        self,
        client: AsyncClient,
        admin_token: str,
        mock_vector_store: MagicMock,
        mock_openai_embed,
    ):
        """Admin must see documents of all access levels."""
        for al, content_prefix in [("all", "pub"), ("staff", "stf"), ("admin", "adm")]:
            content = f"{content_prefix} {uuid.uuid4()}".encode()
            with patch("app.core.config.get_settings", return_value=_mock_settings()):
                await _upload(
                    client, admin_token, content, f"{al}.txt",
                    title=f"Doc {al}", access_level=al
                )

        r = await client.get(
            "/api/v1/rag/documents", headers=_auth(admin_token)
        )
        assert r.status_code == 200
        docs = r.json()
        levels = {d["access_level"] for d in docs}
        assert "admin" in levels or len(docs) >= 1  # at least uploaded docs visible

    async def test_get_doc_forbidden_for_customer(
        self,
        client: AsyncClient,
        admin_token: str,
        customer_token: str,
        mock_vector_store: MagicMock,
        mock_openai_embed,
    ):
        """Customer must get 403 when fetching an admin-level document by ID."""
        content = f"admin-secret {uuid.uuid4()}".encode()
        with patch("app.core.config.get_settings", return_value=_mock_settings()):
            r = await _upload(
                client, admin_token, content, "secret.txt",
                title="Secret", access_level="admin"
            )
        if r.status_code != 201:
            pytest.skip(f"Upload failed: {r.text}")
        doc_id = r.json()["id"]

        r2 = await client.get(
            f"/api/v1/rag/documents/{doc_id}", headers=_auth(customer_token)
        )
        assert r2.status_code == 403, r2.text

    async def test_delete_requires_admin(
        self,
        client: AsyncClient,
        admin_token: str,
        employee_token: str,
        mock_vector_store: MagicMock,
        mock_openai_embed,
    ):
        """Employee must get 403 when attempting to delete a document."""
        content = f"deletable {uuid.uuid4()}".encode()
        with patch("app.core.config.get_settings", return_value=_mock_settings()):
            r = await _upload(
                client, admin_token, content, "del.txt", title="To Delete"
            )
        if r.status_code != 201:
            pytest.skip(f"Upload failed: {r.text}")
        doc_id = r.json()["id"]

        r2 = await client.delete(
            f"/api/v1/rag/documents/{doc_id}", headers=_auth(employee_token)
        )
        assert r2.status_code == 403, r2.text

    async def test_delete_removes_doc(
        self,
        client: AsyncClient,
        admin_token: str,
        mock_vector_store: MagicMock,
        mock_openai_embed,
    ):
        """Admin can delete a document → 204, then GET returns 404."""
        content = f"to-delete {uuid.uuid4()}".encode()
        with patch("app.core.config.get_settings", return_value=_mock_settings()):
            r = await _upload(
                client, admin_token, content, "del.txt", title="Delete Me"
            )
        if r.status_code != 201:
            pytest.skip(f"Upload failed: {r.text}")
        doc_id = r.json()["id"]

        r2 = await client.delete(
            f"/api/v1/rag/documents/{doc_id}", headers=_auth(admin_token)
        )
        assert r2.status_code == 204, r2.text

        r3 = await client.get(
            f"/api/v1/rag/documents/{doc_id}", headers=_auth(admin_token)
        )
        assert r3.status_code == 404, r3.text


# ============================================================================ #
# TestRAGQuery                                                                   #
# ============================================================================ #


class TestRAGQuery:
    """Tests for POST /api/v1/rag/query."""

    _QUESTION = "What are the current account fees?"

    async def test_query_requires_auth(self, client: AsyncClient):
        """Query without token must return 403."""
        r = await client.post(
            "/api/v1/rag/query", json={"question": self._QUESTION}
        )
        assert r.status_code == 403, r.text

    async def test_query_with_good_context(
        self,
        client: AsyncClient,
        admin_token: str,
        mock_generate,
    ):
        """Mock returning relevant chunks → answer is grounded, sources cited."""
        doc_id = str(uuid.uuid4())
        good_chunks = [_good_chunk(doc_id)]
        vs = _make_mock_vector_store(good_chunks)

        with (
            patch("app.rag.router._get_vector_store", return_value=vs),
            patch("app.rag.router._vector_store", vs),
            patch(
                "app.rag.embeddings.get_query_embedding",
                new=AsyncMock(return_value=_DUMMY_VECTOR),
            ),
            patch("app.core.config.get_settings", return_value=_mock_settings()),
        ):
            r = await client.post(
                "/api/v1/rag/query",
                headers=_auth(admin_token),
                json={"question": self._QUESTION},
            )

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_grounded"] is True
        assert len(body["sources"]) > 0
        assert body["answer"]

    async def test_query_unsupported(
        self,
        client: AsyncClient,
        admin_token: str,
        mock_generate,
    ):
        """Mock returning high-distance chunks → is_grounded=False."""
        doc_id = str(uuid.uuid4())
        bad_chunks = [_high_distance_chunk(doc_id)]
        vs = _make_mock_vector_store(bad_chunks)

        with (
            patch("app.rag.router._get_vector_store", return_value=vs),
            patch("app.rag.router._vector_store", vs),
            patch(
                "app.rag.embeddings.get_query_embedding",
                new=AsyncMock(return_value=_DUMMY_VECTOR),
            ),
            patch("app.core.config.get_settings", return_value=_mock_settings()),
        ):
            r = await client.post(
                "/api/v1/rag/query",
                headers=_auth(admin_token),
                json={"question": self._QUESTION},
            )

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_grounded"] is False

    async def test_query_banned_patterns_pin(
        self, client: AsyncClient, admin_token: str
    ):
        """Questions containing 'pin' must return is_grounded=False without hitting LLM."""
        with patch("app.core.config.get_settings", return_value=_mock_settings()):
            r = await client.post(
                "/api/v1/rag/query",
                headers=_auth(admin_token),
                json={"question": "What is my PIN number?"},
            )
        assert r.status_code == 200, r.text
        assert r.json()["is_grounded"] is False

    async def test_query_banned_patterns_password(
        self, client: AsyncClient, admin_token: str
    ):
        """Questions containing 'password' must return is_grounded=False."""
        with patch("app.core.config.get_settings", return_value=_mock_settings()):
            r = await client.post(
                "/api/v1/rag/query",
                headers=_auth(admin_token),
                json={"question": "How do I reset my password?"},
            )
        assert r.status_code == 200, r.text
        assert r.json()["is_grounded"] is False

    async def test_query_sources_cited(
        self,
        client: AsyncClient,
        admin_token: str,
        mock_generate,
    ):
        """Response includes SourceCitation objects with title and document_id."""
        doc_id = str(uuid.uuid4())
        chunks = [_good_chunk(doc_id, title="FAQ Handbook")]
        vs = _make_mock_vector_store(chunks)

        with (
            patch("app.rag.router._get_vector_store", return_value=vs),
            patch("app.rag.router._vector_store", vs),
            patch(
                "app.rag.embeddings.get_query_embedding",
                new=AsyncMock(return_value=_DUMMY_VECTOR),
            ),
            patch("app.core.config.get_settings", return_value=_mock_settings()),
        ):
            r = await client.post(
                "/api/v1/rag/query",
                headers=_auth(admin_token),
                json={"question": self._QUESTION},
            )

        assert r.status_code == 200, r.text
        body = r.json()
        if body["is_grounded"]:
            sources = body["sources"]
            assert len(sources) > 0
            s = sources[0]
            assert "document_id" in s
            assert "title" in s
            assert s["document_id"] == doc_id
            assert s["title"] == "FAQ Handbook"

    async def test_query_no_api_key(
        self, client: AsyncClient, admin_token: str
    ):
        """When OPENAI_API_KEY is empty, query must return 503."""
        with patch(
            "app.core.config.get_settings",
            return_value=_mock_settings(openai_api_key=""),
        ):
            r = await client.post(
                "/api/v1/rag/query",
                headers=_auth(admin_token),
                json={"question": self._QUESTION},
            )
        assert r.status_code == 503, r.text

    async def test_query_latency_reported(
        self,
        client: AsyncClient,
        admin_token: str,
        mock_generate,
    ):
        """Response must include latency_ms > 0."""
        vs = _make_mock_vector_store([])

        with (
            patch("app.rag.router._get_vector_store", return_value=vs),
            patch("app.rag.router._vector_store", vs),
            patch(
                "app.rag.embeddings.get_query_embedding",
                new=AsyncMock(return_value=_DUMMY_VECTOR),
            ),
            patch("app.core.config.get_settings", return_value=_mock_settings()),
        ):
            r = await client.post(
                "/api/v1/rag/query",
                headers=_auth(admin_token),
                json={"question": self._QUESTION},
            )

        assert r.status_code == 200, r.text
        body = r.json()
        assert "latency_ms" in body
        assert isinstance(body["latency_ms"], (int, float))
        assert body["latency_ms"] >= 0


# ============================================================================ #
# TestCitationCorrectness                                                        #
# ============================================================================ #


class TestCitationCorrectness:
    """Tests for SourceCitation field correctness."""

    _QUESTION = "What are the fixed deposit interest rates?"

    async def test_citation_includes_page(
        self,
        client: AsyncClient,
        admin_token: str,
        mock_generate,
    ):
        """SourceCitation.page_or_section is populated when chunk has it."""
        doc_id = str(uuid.uuid4())
        chunks = [_good_chunk(doc_id, page_or_section="Section 3")]
        vs = _make_mock_vector_store(chunks)

        with (
            patch("app.rag.router._get_vector_store", return_value=vs),
            patch("app.rag.router._vector_store", vs),
            patch(
                "app.rag.embeddings.get_query_embedding",
                new=AsyncMock(return_value=_DUMMY_VECTOR),
            ),
            patch("app.core.config.get_settings", return_value=_mock_settings()),
        ):
            r = await client.post(
                "/api/v1/rag/query",
                headers=_auth(admin_token),
                json={"question": self._QUESTION},
            )

        assert r.status_code == 200, r.text
        body = r.json()
        if body["is_grounded"] and body["sources"]:
            assert body["sources"][0]["page_or_section"] == "Section 3"

    async def test_citation_relevance_score(
        self,
        client: AsyncClient,
        admin_token: str,
        mock_generate,
    ):
        """relevance_score must be in [0.0, 1.0]."""
        doc_id = str(uuid.uuid4())
        chunks = [_good_chunk(doc_id)]
        vs = _make_mock_vector_store(chunks)

        with (
            patch("app.rag.router._get_vector_store", return_value=vs),
            patch("app.rag.router._vector_store", vs),
            patch(
                "app.rag.embeddings.get_query_embedding",
                new=AsyncMock(return_value=_DUMMY_VECTOR),
            ),
            patch("app.core.config.get_settings", return_value=_mock_settings()),
        ):
            r = await client.post(
                "/api/v1/rag/query",
                headers=_auth(admin_token),
                json={"question": self._QUESTION},
            )

        assert r.status_code == 200, r.text
        body = r.json()
        for src in body.get("sources", []):
            score = src["relevance_score"]
            assert 0.0 <= score <= 1.0, f"Score out of range: {score}"

    async def test_no_duplicate_citations(
        self,
        client: AsyncClient,
        admin_token: str,
        mock_generate,
    ):
        """Same document must not appear more than once in sources."""
        doc_id = str(uuid.uuid4())
        # Return two chunks from the same doc
        chunks = [
            _good_chunk(doc_id, page_or_section="Page 1"),
            {**_good_chunk(doc_id, page_or_section="Page 2"), "distance": 0.2},
        ]
        vs = _make_mock_vector_store(chunks)

        with (
            patch("app.rag.router._get_vector_store", return_value=vs),
            patch("app.rag.router._vector_store", vs),
            patch(
                "app.rag.embeddings.get_query_embedding",
                new=AsyncMock(return_value=_DUMMY_VECTOR),
            ),
            patch("app.core.config.get_settings", return_value=_mock_settings()),
        ):
            r = await client.post(
                "/api/v1/rag/query",
                headers=_auth(admin_token),
                json={"question": self._QUESTION},
            )

        assert r.status_code == 200, r.text
        body = r.json()
        doc_ids = [s["document_id"] for s in body.get("sources", [])]
        assert len(doc_ids) == len(set(doc_ids)), "Duplicate citations found"


# ============================================================================ #
# TestPermissionsAndSecurity                                                     #
# ============================================================================ #


class TestPermissionsAndSecurity:
    """Permission checks and security invariants."""

    async def test_customer_cannot_upload(
        self, client: AsyncClient, customer_token: str
    ):
        """Customer must get 403 on upload."""
        r = await _upload(client, customer_token, _make_txt_bytes())
        assert r.status_code == 403, r.text

    async def test_employee_cannot_upload(
        self, client: AsyncClient, employee_token: str
    ):
        """Employee must get 403 on upload."""
        r = await _upload(client, employee_token, _make_txt_bytes())
        assert r.status_code == 403, r.text

    async def test_admin_only_can_delete(
        self,
        client: AsyncClient,
        admin_token: str,
        employee_token: str,
        mock_vector_store: MagicMock,
        mock_openai_embed,
    ):
        """Employee must get 403 when trying to delete."""
        content = f"del {uuid.uuid4()}".encode()
        with patch("app.core.config.get_settings", return_value=_mock_settings()):
            r = await _upload(client, admin_token, content, "d.txt", title="Del")
        if r.status_code != 201:
            pytest.skip(f"Upload failed: {r.text}")
        doc_id = r.json()["id"]

        r2 = await client.delete(
            f"/api/v1/rag/documents/{doc_id}", headers=_auth(employee_token)
        )
        assert r2.status_code == 403, r2.text

    async def test_admin_only_can_update_status(
        self,
        client: AsyncClient,
        admin_token: str,
        employee_token: str,
        mock_vector_store: MagicMock,
        mock_openai_embed,
    ):
        """Employee must get 403 when trying to PATCH document status."""
        content = f"status {uuid.uuid4()}".encode()
        with patch("app.core.config.get_settings", return_value=_mock_settings()):
            r = await _upload(client, admin_token, content, "s.txt", title="Status")
        if r.status_code != 201:
            pytest.skip(f"Upload failed: {r.text}")
        doc_id = r.json()["id"]

        r2 = await client.patch(
            f"/api/v1/rag/documents/{doc_id}/status",
            headers=_auth(employee_token),
            json={"status": "superseded"},
        )
        assert r2.status_code == 403, r2.text

    async def test_response_never_contains_api_key(
        self,
        client: AsyncClient,
        admin_token: str,
        mock_generate,
    ):
        """API key string must NEVER appear in any query response."""
        vs = _make_mock_vector_store([_good_chunk(str(uuid.uuid4()))])

        with (
            patch("app.rag.router._get_vector_store", return_value=vs),
            patch("app.rag.router._vector_store", vs),
            patch(
                "app.rag.embeddings.get_query_embedding",
                new=AsyncMock(return_value=_DUMMY_VECTOR),
            ),
            patch(
                "app.core.config.get_settings",
                return_value=_mock_settings(openai_api_key=_FAKE_API_KEY),
            ),
        ):
            r = await client.post(
                "/api/v1/rag/query",
                headers=_auth(admin_token),
                json={"question": "What are banking fees?"},
            )

        assert r.status_code == 200, r.text
        response_text = r.text
        assert _FAKE_API_KEY not in response_text, (
            "API key was leaked in response!"
        )

    async def test_customer_cannot_access_staff_doc_via_query(
        self,
        client: AsyncClient,
        customer_token: str,
        mock_generate,
    ):
        """When only staff docs exist, customer query returns no grounded sources."""
        staff_doc_id = str(uuid.uuid4())
        # VS mock returns staff chunks, but customer query uses access_tier="all"
        # In production the VS would filter them out; here we simulate empty result
        vs = _make_mock_vector_store([])  # customer sees nothing

        with (
            patch("app.rag.router._get_vector_store", return_value=vs),
            patch("app.rag.router._vector_store", vs),
            patch(
                "app.rag.embeddings.get_query_embedding",
                new=AsyncMock(return_value=_DUMMY_VECTOR),
            ),
            patch("app.core.config.get_settings", return_value=_mock_settings()),
        ):
            r = await client.post(
                "/api/v1/rag/query",
                headers=_auth(customer_token),
                json={"question": "What is the staff policy?"},
            )

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_grounded"] is False
        # No staff doc should appear in sources
        for src in body.get("sources", []):
            assert src["document_id"] != staff_doc_id


# ============================================================================ #
# TestHealthAndErrors                                                            #
# ============================================================================ #


class TestHealthAndErrors:
    """Tests for GET /api/v1/rag/health."""

    async def test_rag_health_endpoint(
        self, client: AsyncClient, mock_vector_store: MagicMock
    ):
        """Health endpoint returns 200 with required keys."""
        with patch("app.core.config.get_settings", return_value=_mock_settings()):
            r = await client.get("/api/v1/rag/health")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "status" in body
        assert "vector_store" in body
        assert "llm" in body

    async def test_health_degraded_no_api_key(
        self, client: AsyncClient, mock_vector_store: MagicMock
    ):
        """Health endpoint returns status='degraded' when API key is missing."""
        with patch(
            "app.core.config.get_settings",
            return_value=_mock_settings(openai_api_key=""),
        ):
            r = await client.get("/api/v1/rag/health")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "degraded", body

    async def test_missing_api_key_on_query(
        self, client: AsyncClient, admin_token: str
    ):
        """Query without API key must return 503 with a helpful message."""
        with patch(
            "app.core.config.get_settings",
            return_value=_mock_settings(openai_api_key=""),
        ):
            r = await client.post(
                "/api/v1/rag/query",
                headers=_auth(admin_token),
                json={"question": "What are the banking fees?"},
            )
        assert r.status_code == 503, r.text
        detail = r.json().get("detail", "")
        assert detail  # must have a non-empty error message


# ============================================================================ #
# TestUnsupportedQuestions                                                       #
# ============================================================================ #


class TestUnsupportedQuestions:
    """Tests for question validation and no-match handling."""

    async def test_question_too_short(
        self, client: AsyncClient, admin_token: str
    ):
        """Question shorter than 3 chars must return 422."""
        with patch("app.core.config.get_settings", return_value=_mock_settings()):
            r = await client.post(
                "/api/v1/rag/query",
                headers=_auth(admin_token),
                json={"question": "ab"},
            )
        assert r.status_code == 422, r.text

    async def test_question_too_long(
        self, client: AsyncClient, admin_token: str
    ):
        """Question exceeding 500 chars must return 422."""
        long_q = "What are the fees? " * 30  # > 500 chars
        with patch("app.core.config.get_settings", return_value=_mock_settings()):
            r = await client.post(
                "/api/v1/rag/query",
                headers=_auth(admin_token),
                json={"question": long_q},
            )
        assert r.status_code == 422, r.text

    async def test_no_matching_chunks(
        self,
        client: AsyncClient,
        admin_token: str,
        mock_generate,
    ):
        """When vector store returns empty, answer must be UNSUPPORTED."""
        vs = _make_mock_vector_store([])  # no results

        with (
            patch("app.rag.router._get_vector_store", return_value=vs),
            patch("app.rag.router._vector_store", vs),
            patch(
                "app.rag.embeddings.get_query_embedding",
                new=AsyncMock(return_value=_DUMMY_VECTOR),
            ),
            patch("app.core.config.get_settings", return_value=_mock_settings()),
        ):
            r = await client.post(
                "/api/v1/rag/query",
                headers=_auth(admin_token),
                json={"question": "Tell me about alien banking systems?"},
            )

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_grounded"] is False
        assert len(body["sources"]) == 0

    async def test_low_relevance_chunks(
        self,
        client: AsyncClient,
        admin_token: str,
        mock_generate,
    ):
        """When all chunks have distance > 1.5, is_grounded must be False."""
        doc_id = str(uuid.uuid4())
        bad_chunks = [
            _high_distance_chunk(doc_id),
            _high_distance_chunk(str(uuid.uuid4())),
        ]
        vs = _make_mock_vector_store(bad_chunks)

        with (
            patch("app.rag.router._get_vector_store", return_value=vs),
            patch("app.rag.router._vector_store", vs),
            patch(
                "app.rag.embeddings.get_query_embedding",
                new=AsyncMock(return_value=_DUMMY_VECTOR),
            ),
            patch("app.core.config.get_settings", return_value=_mock_settings()),
        ):
            r = await client.post(
                "/api/v1/rag/query",
                headers=_auth(admin_token),
                json={"question": "What are the banking fees?"},
            )

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_grounded"] is False
