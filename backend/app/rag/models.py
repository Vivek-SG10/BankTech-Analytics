"""
SQLAlchemy ORM model for the RAG knowledge-base documents table.

Uses the same Column() style as auth/models.py and surveys/models.py
so it is compatible with Python 3.14 and the shared declarative Base.

Raw file content is NEVER stored here — only metadata and chunk counts.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
)

from app.auth.models import Base


class KBDocumentOrm(Base):
    """
    Persisted metadata for every document ingested into the knowledge base.

    Lifecycle statuses
    ------------------
    active      — the current, authoritative version of this document
    superseded  — an older version that has been replaced (not deleted)

    Access levels
    -------------
    all    — visible to every authenticated user (including customer)
    staff  — visible to employee, manager, researcher, admin
    admin  — visible to admin only
    """

    __tablename__ = "rag_documents"

    # ── Primary key ───────────────────────────────────────────────────────
    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="UUID primary key (string form)",
    )

    # ── Document identity ─────────────────────────────────────────────────
    title = Column(String(255), nullable=False, comment="Human-readable document title")
    filename = Column(String(255), nullable=False, comment="Original uploaded filename")
    file_type = Column(String(10), nullable=False, comment="pdf | txt | docx")
    file_size_bytes = Column(Integer, nullable=False, comment="Raw byte size")

    # ── Deduplication ─────────────────────────────────────────────────────
    content_hash = Column(
        String(64),
        nullable=False,
        unique=True,
        comment="SHA-256 hex digest of raw file bytes",
    )

    # ── Lifecycle ─────────────────────────────────────────────────────────
    status = Column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
        comment="active | superseded",
    )
    version = Column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
        comment="Monotonically increasing version counter",
    )

    # ── Provenance ────────────────────────────────────────────────────────
    uploaded_by = Column(
        String(36),
        nullable=False,
        comment="UUID of the user who uploaded this document",
    )
    uploaded_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Timestamp of upload (server-generated)",
    )

    # ── Access control ────────────────────────────────────────────────────
    access_level = Column(
        String(20),
        nullable=False,
        default="all",
        server_default="all",
        comment="all | staff | admin",
    )

    # ── Indexing metadata ─────────────────────────────────────────────────
    chunk_count = Column(Integer, nullable=True, comment="Chunks stored in vector store")
    indexed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of successful indexing",
    )

    # ── Optional description ──────────────────────────────────────────────
    description = Column(Text, nullable=True, comment="Free-text description")

    # ── Composite indexes ─────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_rag_documents_content_hash", "content_hash", unique=True),
        Index("ix_rag_documents_status", "status"),
        Index("ix_rag_documents_access_level", "access_level"),
        Index("ix_rag_documents_uploaded_by", "uploaded_by"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<KBDocumentOrm id={self.id!r} title={self.title!r} "
            f"status={self.status!r} version={self.version}>"
        )
