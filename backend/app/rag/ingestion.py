"""
Document ingestion pipeline for the BankTech RAG knowledge base.

Optional dependencies (pypdf, python-docx) are imported lazily; the server
starts without them and returns HTTP 501 only when a request actually requires
the missing library.

Security notes
--------------
- File content is treated as untrusted data throughout. No content is ever
  echoed back verbatim in an error message.
- Access levels are set by authenticated staff/admin callers, not derived from
  document content.
- File size and type are validated before any parsing is attempted.
"""

from __future__ import annotations

import hashlib
import io
import logging
import uuid
from typing import Callable

from fastapi import HTTPException

from app.rag.document_store import VectorStore

logger = logging.getLogger(__name__)

# =========================================================================== #
# Constants                                                                    #
# =========================================================================== #

MAX_FILE_SIZE_BYTES: int = 20 * 1024 * 1024  # 20 MB
ALLOWED_TYPES: set[str] = {"pdf", "txt", "docx"}
CHUNK_SIZE: int = 800   # characters per chunk
CHUNK_OVERLAP: int = 150  # overlap between consecutive chunks


# =========================================================================== #
# Validation                                                                   #
# =========================================================================== #


def validate_file(filename: str, content: bytes) -> str:
    """Validate an uploaded file and return its detected type.

    Parameters
    ----------
    filename:
        The original filename as reported by the client.
    content:
        Raw bytes of the uploaded file.

    Returns
    -------
    str
        Detected file extension: one of ``"pdf"``, ``"txt"``, ``"docx"``.

    Raises
    ------
    HTTPException(400)
        When the file is empty or has an unsupported extension.
    HTTPException(413)
        When the file exceeds ``MAX_FILE_SIZE_BYTES``.
    """
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if len(content) > MAX_FILE_SIZE_BYTES:
        limit_mb = MAX_FILE_SIZE_BYTES // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the maximum allowed size of {limit_mb} MB.",
        )

    # Derive file type from extension; never trust MIME type supplied by client.
    parts = filename.rsplit(".", 1)
    if len(parts) != 2:
        raise HTTPException(
            status_code=400,
            detail="Cannot determine file type: filename has no extension.",
        )

    ext = parts[1].lower()
    if ext not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '.{ext}'. Allowed: {sorted(ALLOWED_TYPES)}.",
        )

    return ext


# =========================================================================== #
# Text extraction                                                              #
# =========================================================================== #


def extract_text_with_metadata(content: bytes, file_type: str) -> list[dict]:
    """Extract text segments with positional metadata from raw file bytes.

    Parameters
    ----------
    content:
        Raw bytes of the validated file.
    file_type:
        One of ``"pdf"``, ``"txt"``, ``"docx"``.

    Returns
    -------
    list[dict]
        Each element: ``{"text": str, "page_or_section": str | None}``.

    Raises
    ------
    HTTPException(501)
        When the required parsing library is not installed.
    HTTPException(400)
        When the document cannot be parsed (corrupt file, password-protected, …).
    """
    if file_type == "txt":
        return _extract_txt(content)
    if file_type == "pdf":
        return _extract_pdf(content)
    if file_type == "docx":
        return _extract_docx(content)
    # Should never reach here after validate_file; guard anyway.
    raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_type!r}")


def _extract_txt(content: bytes) -> list[dict]:
    text = content.decode("utf-8", errors="replace")
    return [{"text": text, "page_or_section": None}]


def _extract_pdf(content: bytes) -> list[dict]:
    try:
        import pypdf  # noqa: PLC0415
    except ImportError as exc:
        raise HTTPException(
            status_code=501,
            detail=(
                "PDF processing is not available. "
                "Install it with:  pip install pypdf"
            ),
        ) from exc

    segments: list[dict] = []
    try:
        reader = pypdf.PdfReader(io.BytesIO(content))
        for page_num, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            text = text.strip()
            if text:
                segments.append({"text": text, "page_or_section": f"Page {page_num}"})
    except Exception as exc:
        logger.warning("PDF extraction failed: %s", exc)
        raise HTTPException(
            status_code=400,
            detail="Could not extract text from the PDF. The file may be corrupt or password-protected.",
        ) from exc

    if not segments:
        raise HTTPException(
            status_code=400,
            detail="The PDF contains no extractable text (it may be a scanned image PDF).",
        )

    return segments


def _extract_docx(content: bytes) -> list[dict]:
    try:
        import docx  # noqa: PLC0415  (python-docx)
    except ImportError as exc:
        raise HTTPException(
            status_code=501,
            detail=(
                "DOCX processing is not available. "
                "Install it with:  pip install python-docx"
            ),
        ) from exc

    try:
        document = docx.Document(io.BytesIO(content))
    except Exception as exc:
        logger.warning("DOCX parse failed: %s", exc)
        raise HTTPException(
            status_code=400,
            detail="Could not parse the DOCX file. It may be corrupt or in an unsupported format.",
        ) from exc

    segments: list[dict] = []
    current_section: str | None = None
    buffer: list[str] = []

    # Heading styles recognised as section markers.
    _HEADING_STYLES = {
        "heading 1", "heading 2", "heading 3",
        "heading1", "heading2", "heading3",
        "title",
    }

    def _flush_buffer() -> None:
        text = " ".join(buffer).strip()
        if text:
            segments.append({"text": text, "page_or_section": current_section})
        buffer.clear()

    for para in document.paragraphs:
        style_name = (para.style.name or "").lower()
        para_text = para.text.strip()

        if not para_text:
            continue

        if style_name in _HEADING_STYLES:
            # Flush accumulated non-heading paragraphs under the previous section.
            _flush_buffer()
            current_section = para_text
        else:
            buffer.append(para_text)

    # Flush anything remaining after the last heading.
    _flush_buffer()

    if not segments:
        raise HTTPException(
            status_code=400,
            detail="The DOCX file contains no extractable text.",
        )

    return segments


# =========================================================================== #
# Chunking                                                                     #
# =========================================================================== #


def chunk_text(
    text: str,
    page_or_section: str | None,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[dict]:
    """Split *text* into overlapping fixed-size character windows.

    Parameters
    ----------
    text:
        Source text to chunk.
    page_or_section:
        Provenance tag propagated to every chunk produced from this text.
    chunk_size:
        Target character count per chunk.
    overlap:
        Number of characters shared between consecutive chunks.

    Returns
    -------
    list[dict]
        Each element: ``{"text": str, "page_or_section": str | None, "chunk_index": int}``.
    """
    if not text:
        return []

    step = max(chunk_size - overlap, 1)
    chunks: list[dict] = []
    index = 0
    pos = 0

    while pos < len(text):
        window = text[pos: pos + chunk_size]
        chunks.append(
            {
                "text": window,
                "page_or_section": page_or_section,
                "chunk_index": index,
            }
        )
        index += 1
        pos += step

    return chunks


# =========================================================================== #
# Hashing                                                                      #
# =========================================================================== #


def compute_hash(content: bytes) -> str:
    """Return the SHA-256 hex digest of *content*."""
    return hashlib.sha256(content).hexdigest()


# =========================================================================== #
# Orchestration                                                                #
# =========================================================================== #


async def ingest_document(
    content: bytes,
    filename: str,
    title: str,
    description: str | None,
    access_level: str,
    uploader_id: str,
    vector_store: VectorStore,
    embedding_fn: Callable,  # async (texts: list[str]) -> list[list[float]]
    doc_id: str | None = None,  # caller-supplied UUID; generated internally if None
) -> dict:
    """Orchestrate the full ingestion pipeline for a single document.

    Pipeline
    --------
    validate → extract text → chunk → embed → upsert into vector store

    Parameters
    ----------
    content:
        Raw file bytes.
    filename:
        Original uploaded filename (used for type detection).
    title:
        Human-readable document title stored in metadata.
    description:
        Optional free-text description; not indexed into the vector store.
    access_level:
        ``"all"`` | ``"staff"`` | ``"admin"`` — controls who can retrieve chunks.
    uploader_id:
        UUID string of the authenticated uploader.
    vector_store:
        Initialised ``VectorStore`` instance.
    embedding_fn:
        Async callable ``(texts: list[str]) -> list[list[float]]``.

    Returns
    -------
    dict
        ``{"doc_id": str, "content_hash": str, "chunk_count": int, "status": "indexed"}``

    Raises
    ------
    HTTPException
        Propagated from ``validate_file`` or ``extract_text_with_metadata``.
    """
    # 1. Validate ----------------------------------------------------------------
    file_type = validate_file(filename, content)
    content_hash = compute_hash(content)
    if doc_id is None:
        doc_id = str(uuid.uuid4())

    logger.info(
        "Ingesting document doc_id=%r filename=%r file_type=%r size=%d bytes",
        doc_id,
        filename,
        file_type,
        len(content),
    )

    # 2. Extract text with positional metadata -----------------------------------
    segments = extract_text_with_metadata(content, file_type)

    # 3. Chunk each segment ------------------------------------------------------
    all_chunks: list[dict] = []
    for segment in segments:
        sub_chunks = chunk_text(
            text=segment["text"],
            page_or_section=segment["page_or_section"],
        )
        all_chunks.extend(sub_chunks)

    if not all_chunks:
        raise HTTPException(
            status_code=400,
            detail="No text could be extracted from the document.",
        )

    # 4. Embed all chunk texts in one (batched) call -----------------------------
    texts = [c["text"] for c in all_chunks]
    embeddings: list[list[float]] = await embedding_fn(texts)

    if len(embeddings) != len(all_chunks):
        raise HTTPException(
            status_code=500,
            detail=f"Embedding service returned {len(embeddings)} vectors for {len(all_chunks)} chunks.",
        )

    # 5. Build VectorStore chunk records with globally unique IDs ----------------
    vs_chunks: list[dict] = []
    for idx, (chunk, embedding) in enumerate(zip(all_chunks, embeddings)):
        chunk_id = f"{doc_id}__chunk__{idx}"
        vs_chunks.append(
            {
                "id": chunk_id,
                "text": chunk["text"],
                "embedding": embedding,
                "metadata": {
                    "doc_id": doc_id,
                    "title": title,
                    "page_or_section": chunk.get("page_or_section"),
                    "file_type": file_type,
                    "access_level": access_level,
                    "chunk_index": chunk["chunk_index"],
                },
            }
        )

    # Repack for VectorStore.add_chunks (which uses collection.upsert with
    # embeddings provided separately via the chromadb API).
    # We pass the embedding alongside the chunk so add_chunks can forward it.
    vector_store.add_chunks(vs_chunks)

    chunk_count = len(vs_chunks)
    logger.info(
        "Document doc_id=%r indexed successfully: %d chunks, access_level=%r",
        doc_id,
        chunk_count,
        access_level,
    )

    return {
        "doc_id": doc_id,
        "content_hash": content_hash,
        "chunk_count": chunk_count,
        "status": "indexed",
    }
