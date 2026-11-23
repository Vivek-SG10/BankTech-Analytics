"""
Pydantic v2 schemas for the RAG / Knowledge-Base subsystem.

Security note
-------------
Raw document content is intentionally excluded from all outbound schemas.
The OpenAI API key is never serialised into any response object.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# =========================================================================== #
# Document schemas                                                             #
# =========================================================================== #


class DocumentOut(BaseModel):
    """Full safe read-only view of a knowledge-base document.

    Raw file bytes and content hashes are excluded intentionally.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    filename: str
    file_type: str
    file_size_bytes: int
    status: str
    version: int
    uploaded_by: str
    uploaded_at: datetime
    access_level: str
    chunk_count: int | None
    indexed_at: datetime | None
    description: str | None


class DocumentListItem(BaseModel):
    """Lightweight projection used in paginated list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    filename: str
    file_type: str
    status: str
    version: int
    access_level: str
    uploaded_at: datetime
    chunk_count: int | None


class DocumentStatusUpdate(BaseModel):
    """Payload for PATCH /documents/{id}/status."""

    status: Literal["active", "superseded"]


# =========================================================================== #
# Query schemas                                                                #
# =========================================================================== #


class QueryRequest(BaseModel):
    """Incoming question from a client."""

    question: Annotated[
        str,
        Field(
            min_length=1,
            max_length=4000,
            description="The question to ask the knowledge base.",
        ),
    ]
    top_k: Annotated[
        int,
        Field(
            default=5,
            ge=1,
            le=20,
            description="Maximum number of document chunks to retrieve (1–20).",
        ),
    ] = 5


class SourceCitation(BaseModel):
    """A single source document excerpt that contributed to an answer."""

    document_id: str
    title: str
    page_or_section: str | None = None
    relevance_score: float = Field(
        description="Normalised relevance score in [0, 1] where 1 = most relevant.",
    )


class QueryResponse(BaseModel):
    """Full response returned to the client after a RAG query."""

    answer: str = Field(
        description="Generated answer. Never contains credentials or internal keys.",
    )
    sources: list[SourceCitation] = Field(
        default_factory=list,
        description="Document excerpts the answer is grounded in.",
    )
    is_grounded: bool = Field(
        description=(
            "True when the answer is derived from retrieved document excerpts. "
            "False when no sufficiently relevant chunks were found."
        ),
    )
    latency_ms: float = Field(
        description="Wall-clock time for the full RAG pipeline in milliseconds.",
    )


# =========================================================================== #
# Health schema                                                                #
# =========================================================================== #


class HealthResponse(BaseModel):
    """Diagnostic status for the RAG subsystem components."""

    status: str = Field(description="Overall status: ok | degraded | error")
    vector_store: str = Field(description="ChromaDB status: ok | error | unavailable")
    llm: str = Field(description="OpenAI LLM status: ok | error | unconfigured")
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional diagnostic key/value pairs (never includes API keys).",
    )
