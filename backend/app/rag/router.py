"""
RAG API endpoints — BankTech Analytics.
"""
from __future__ import annotations
import time, io, hashlib, uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user, require_roles
from app.auth.models import UserOrm
from app.core.config import get_settings
from app.core.database import get_db
from app.rag.models import KBDocumentOrm
from app.rag.schemas import (
    DocumentOut, DocumentListItem, QueryRequest, QueryResponse,
    SourceCitation, HealthResponse, DocumentStatusUpdate
)

rag_router = APIRouter()

# ── Lazy singletons ──────────────────────────────────────────────────────────
_vector_store = None
def _get_vector_store():
    global _vector_store
    if _vector_store is None:
        from app.rag.document_store import VectorStore
        settings = get_settings()
        _vector_store = VectorStore(settings.chroma_persist_directory)
    return _vector_store

def _access_level_for_role(role: str) -> str:
    """Map user role to access tier string used in vector store filtering."""
    if role == "admin":
        return "admin"
    if role in ("employee", "manager", "researcher"):
        return "staff"
    return "all"  # customer

# ── Upload endpoint (admin only) ─────────────────────────────────────────────
@rag_router.post(
    "/documents",
    status_code=201,
    summary="[Admin] Upload a knowledge-base document",
    response_model=DocumentOut,
)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(..., min_length=1, max_length=255),
    description: str | None = Form(default=None, max_length=1000),
    access_level: str = Form(default="all", pattern="^(all|staff|admin)$"),
    actor: UserOrm = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Upload PDF, TXT or DOCX. Validates file type, size and content. Deduplicates by content hash."""
    from app.rag.ingestion import validate_file, ingest_document, compute_hash
    from app.rag.embeddings import get_embeddings

    try:
        content = await file.read()
        file_type = validate_file(file.filename or "", content)
        content_hash = compute_hash(content)

        # Deduplication check
        existing = await db.execute(select(KBDocumentOrm).where(KBDocumentOrm.content_hash == content_hash))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Document with identical content already exists in the knowledge base.")

        settings = get_settings()
        if not settings.effective_api_key:
            raise HTTPException(status_code=503, detail="LLM API key not configured. Set GEMINI_API_KEY (or OPENAI_API_KEY).")

        doc_id = str(uuid.uuid4())
        vector_store = _get_vector_store()

        async def _embed(texts):
            return await get_embeddings(texts, settings.effective_api_key)

        result = await ingest_document(
            content=content, filename=file.filename or "upload",
            title=title, description=description,
            access_level=access_level, uploader_id=actor.id,
            doc_id=doc_id, vector_store=vector_store, embedding_fn=_embed,
        )

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        doc_orm = KBDocumentOrm(
            id=doc_id, title=title, filename=file.filename or "upload",
            file_type=file_type, file_size_bytes=len(content),
            content_hash=content_hash, status="active",
            version=1, uploaded_by=actor.id, access_level=access_level,
            chunk_count=result["chunk_count"], description=description,
            uploaded_at=now,
            indexed_at=now,
        )
        db.add(doc_orm)
        await db.commit()
        await db.refresh(doc_orm)
        return doc_orm
    except HTTPException:
        raise
    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception("Upload document failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {type(exc).__name__}: {str(exc)}",
        ) from exc


# ── List documents ────────────────────────────────────────────────────────────
@rag_router.get(
    "/documents",
    response_model=list[DocumentListItem],
    summary="List knowledge-base documents",
)
async def list_documents(
    status_filter: str | None = Query(default=None, alias="status", pattern="^(active|superseded)$"),
    actor: UserOrm = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """All authenticated users can list documents they have access to."""
    access_tier = _access_level_for_role(actor.role)
    
    q = select(KBDocumentOrm)
    if status_filter:
        q = q.where(KBDocumentOrm.status == status_filter)
    
    # Filter by access_level based on role
    if access_tier == "all":
        q = q.where(KBDocumentOrm.access_level == "all")
    elif access_tier == "staff":
        q = q.where(KBDocumentOrm.access_level.in_(["all", "staff"]))
    # admin: no filter — sees everything

    q = q.order_by(KBDocumentOrm.uploaded_at.desc())
    rows = (await db.execute(q)).scalars().all()
    return rows


# ── Get document metadata ─────────────────────────────────────────────────────
@rag_router.get("/documents/{doc_id}", response_model=DocumentOut, summary="Get document metadata")
async def get_document(
    doc_id: str,
    actor: UserOrm = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(KBDocumentOrm, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    
    access_tier = _access_level_for_role(actor.role)
    # Enforce access: customer can only see "all" docs
    if access_tier == "all" and doc.access_level != "all":
        raise HTTPException(status_code=403, detail="You do not have access to this document.")
    if access_tier == "staff" and doc.access_level == "admin":
        raise HTTPException(status_code=403, detail="You do not have access to this document.")
    
    return doc


# ── Re-index document (admin only) ────────────────────────────────────────────
@rag_router.post(
    "/documents/{doc_id}/reindex",
    response_model=DocumentOut,
    summary="[Admin] Re-index a document",
)
async def reindex_document(
    doc_id: str,
    actor: UserOrm = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Re-process and re-embed an existing document."""
    raise HTTPException(status_code=501, detail="Re-indexing from stored content is not yet implemented. Delete and re-upload.")


# ── Update document status (admin only) ───────────────────────────────────────
@rag_router.patch(
    "/documents/{doc_id}/status",
    response_model=DocumentOut,
    summary="[Admin] Update document status (active/superseded)",
)
async def update_document_status(
    doc_id: str,
    body: DocumentStatusUpdate,
    actor: UserOrm = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(KBDocumentOrm, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    doc.status = body.status
    await db.commit()
    await db.refresh(doc)
    return doc


# ── Delete document (admin only) ──────────────────────────────────────────────
@rag_router.delete(
    "/documents/{doc_id}",
    status_code=204,
    summary="[Admin] Delete a document from the knowledge base",
)
async def delete_document(
    doc_id: str,
    actor: UserOrm = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(KBDocumentOrm, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    
    try:
        vs = _get_vector_store()
        vs.delete_document(doc_id)
    except Exception:
        pass  # log but don't block DB deletion
    
    await db.delete(doc)
    await db.commit()
    return None


# ── Query endpoint ────────────────────────────────────────────────────────────
@rag_router.post(
    "/query",
    response_model=QueryResponse,
    summary="Ask a banking FAQ question",
)
async def query_knowledge_base(
    body: QueryRequest,
    actor: UserOrm = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve relevant chunks and generate a grounded answer.
    Retrieved content is treated as untrusted reference material only.
    API key is NEVER included in any response.
    """
    t0 = time.monotonic()
    
    settings = get_settings()
    if not settings.effective_api_key:
        raise HTTPException(status_code=503, detail="LLM service not configured. Set GEMINI_API_KEY.")
    
    from app.rag.embeddings import get_query_embedding
    from app.rag.generation import generate_answer

    # Reject banned query patterns (security)
    _BANNED = ["pin", "otp", "password", "secret", "transfer money", "move funds"]
    q_lower = body.question.lower()
    for banned in _BANNED:
        if banned in q_lower:
            from app.rag.generation import UNSUPPORTED_ANSWER
            return QueryResponse(
                answer=UNSUPPORTED_ANSWER + " For security questions, please contact your branch directly.",
                sources=[],
                is_grounded=False,
                latency_ms=round((time.monotonic() - t0) * 1000, 1),
            )
    
    access_tier = _access_level_for_role(actor.role)
    vs = _get_vector_store()
    if vs.collection_count() == 0:
        return QueryResponse(
            answer=(
                "The knowledge base is currently empty. "
                "Please upload approved banking documents (such as FAQ policies) "
                "in the Knowledge Base Management tab before asking questions."
            ),
            sources=[],
            is_grounded=False,
            latency_ms=round((time.monotonic() - t0) * 1000, 1),
        )
    
    try:
        query_emb = await get_query_embedding(body.question, settings.effective_api_key)
        raw_chunks = vs.query(query_emb, body.top_k, access_tier)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Retrieval failed")
        raise HTTPException(status_code=503, detail=f"Retrieval failed: {str(e)}")
    
    result = await generate_answer(
        question=body.question,
        retrieved_chunks=raw_chunks,
        api_key=settings.effective_api_key,
    )
    
    # Build source citations
    seen = set()
    sources = []
    for chunk in result["used_chunks"]:
        meta = chunk.get("metadata", {})
        doc_id = meta.get("doc_id", "")
        if doc_id in seen:
            continue
        seen.add(doc_id)
        sources.append(SourceCitation(
            document_id=doc_id,
            title=meta.get("title", "Unknown"),
            page_or_section=meta.get("page_or_section"),
            relevance_score=round(1.0 - chunk.get("distance", 1.0), 4),
        ))
    
    return QueryResponse(
        answer=result["answer"],
        sources=sources,
        is_grounded=result["is_grounded"],
        latency_ms=round((time.monotonic() - t0) * 1000, 1),
    )


# ── Health ────────────────────────────────────────────────────────────────────
@rag_router.get("/health", response_model=HealthResponse, summary="RAG subsystem health check")
async def rag_health(db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    
    vs_status = "unconfigured"
    vs_details = {}
    try:
        vs = _get_vector_store()
        vs_health = vs.health()
        vs_status = vs_health.get("status", "error")
        vs_details = vs_health
    except Exception as e:
        vs_status = "error"
        vs_details = {"error": type(e).__name__}
    
    llm_status = "configured" if settings.effective_api_key else "not_configured"
    
    # DB check: count documents
    try:
        result = await db.execute(select(KBDocumentOrm))
        docs = result.scalars().all()
        db_details = {"document_count": len(docs), "active": sum(1 for d in docs if d.status == "active")}
    except Exception as e:
        db_details = {"error": type(e).__name__}
    
    return HealthResponse(
        status="ok" if (vs_status == "ok" and llm_status == "configured") else "degraded",
        vector_store=vs_status,
        llm=llm_status,
        details={**vs_details, **db_details},
    )
