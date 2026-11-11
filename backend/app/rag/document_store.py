"""
Vector store wrapper for the BankTech RAG knowledge base.

Supports ChromaDB when installed, with an automatic persistent NumPy fallback
so the application can run in environments without ChromaDB (e.g. Python 3.14).

Access-level filtering
----------------------
Stored chunks carry an ``access_level`` metadata field:
  - "all"   → visible to every role including customer
  - "staff" → visible to employee, manager, researcher, admin
  - "admin" → visible to admin only

The ``query`` method maps the caller's resolved access tier to the set of
document access levels it may read and constructs a filter.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Access-level visibility map: caller tier → allowed doc access_levels
_ACCESS_TIER_MAP: dict[str, list[str]] = {
    "all": ["all"],
    "staff": ["all", "staff"],
    "admin": ["all", "staff", "admin"],
}


class _SimpleVectorStore:
    """Zero-dependency persistent vector store backed by JSON and NumPy."""

    def __init__(self, persist_directory: str, collection_name: str = "banktech_kb") -> None:
        self.persist_dir = Path(persist_directory)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.persist_dir / f"{collection_name}.json"
        self._chunks: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.file_path.exists():
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self._chunks = json.load(f)
            except Exception as e:
                logger.warning("Could not load vector store JSON %s: %s", self.file_path, e)
                self._chunks = {}

    def _save(self) -> None:
        try:
            temp_file = self.file_path.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self._chunks, f)
            temp_file.replace(self.file_path)
        except Exception as e:
            logger.error("Could not save vector store JSON %s: %s", self.file_path, e)

    def add_chunks(self, chunks: list[dict[str, Any]]) -> None:
        for c in chunks:
            chunk_id = c["id"]
            meta = dict(c.get("metadata", {}))
            if meta.get("page_or_section") is None:
                meta["page_or_section"] = ""
            self._chunks[chunk_id] = {
                "id": chunk_id,
                "text": c["text"],
                "metadata": meta,
                "embedding": c.get("embedding", []),
            }
        self._save()

    def query(
        self,
        query_embedding: list[float],
        top_k: int,
        access_level_filter: str,
    ) -> list[dict[str, Any]]:
        allowed_levels = set(_ACCESS_TIER_MAP.get(access_level_filter, ["all"]))
        candidates = [
            c for c in self._chunks.values()
            if c.get("metadata", {}).get("access_level", "all") in allowed_levels
        ]

        if not candidates or not query_embedding:
            return []

        import numpy as np  # noqa: PLC0415
        q = np.array(query_embedding, dtype=np.float32)
        q_norm = float(np.linalg.norm(q))
        if q_norm > 1e-9:
            q = q / q_norm

        scored: list[tuple[float, dict[str, Any]]] = []
        for c in candidates:
            emb = c.get("embedding")
            if emb and len(emb) == len(query_embedding):
                v = np.array(emb, dtype=np.float32)
                v_norm = float(np.linalg.norm(v))
                if v_norm > 1e-9:
                    v = v / v_norm
                cos_sim = float(np.dot(q, v))
                dist = max(0.0, 1.0 - cos_sim)
            else:
                dist = 1.0

            scored.append((dist, {
                "text": c["text"],
                "metadata": c["metadata"],
                "distance": dist,
            }))

        scored.sort(key=lambda x: x[0])
        return [item[1] for item in scored[:top_k]]

    def delete_document(self, doc_id: str) -> None:
        to_del = [cid for cid, c in self._chunks.items() if c.get("metadata", {}).get("doc_id") == doc_id]
        for cid in to_del:
            self._chunks.pop(cid, None)
        self._save()

    def collection_count(self) -> int:
        return len(self._chunks)

    def health(self) -> dict[str, Any]:
        return {"status": "ok", "chunk_count": len(self._chunks), "backend": "numpy"}


class VectorStore:
    """Wrapper around ChromaDB with automatic fallback to persistent NumPy store."""

    def __init__(
        self,
        persist_directory: str,
        collection_name: str = "banktech_kb",
    ) -> None:
        self._collection_name = collection_name
        self._persist_directory = persist_directory
        self._chroma_coll = None
        self._fallback_store = None

        try:
            import chromadb  # noqa: PLC0415
            self._client = chromadb.PersistentClient(path=persist_directory)
            self._chroma_coll = self._client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("ChromaDB initialised: collection=%r persist_dir=%r", collection_name, persist_directory)
        except Exception as exc:
            logger.info("ChromaDB not available (%s); using persistent NumPy vector store fallback.", exc)
            self._fallback_store = _SimpleVectorStore(persist_directory, collection_name)

    def add_chunks(self, chunks: list[dict[str, Any]]) -> None:
        if self._fallback_store is not None:
            self._fallback_store.add_chunks(chunks)
            return

        if not chunks:
            return

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []
        all_have_embeddings = all("embedding" in c for c in chunks)
        embeddings: list[list[float]] | None = [] if all_have_embeddings else None

        for chunk in chunks:
            ids.append(chunk["id"])
            documents.append(chunk["text"])
            meta = dict(chunk["metadata"])
            if meta.get("page_or_section") is None:
                meta["page_or_section"] = ""
            metadatas.append(meta)
            if embeddings is not None:
                embeddings.append(chunk["embedding"])

        upsert_kwargs: dict[str, Any] = {
            "ids": ids,
            "documents": documents,
            "metadatas": metadatas,
        }
        if embeddings is not None:
            upsert_kwargs["embeddings"] = embeddings

        self._chroma_coll.upsert(**upsert_kwargs)

    def query(
        self,
        query_embedding: list[float],
        top_k: int,
        access_level_filter: str,
    ) -> list[dict[str, Any]]:
        if self._fallback_store is not None:
            return self._fallback_store.query(query_embedding, top_k, access_level_filter)

        allowed_levels = _ACCESS_TIER_MAP.get(access_level_filter, ["all"])
        where_clause = (
            {"access_level": {"$eq": allowed_levels[0]}}
            if len(allowed_levels) == 1
            else {"access_level": {"$in": allowed_levels}}
        )

        results = self._chroma_coll.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_clause,
            include=["documents", "metadatas", "distances"],
        )

        output: list[dict[str, Any]] = []
        documents_list = results.get("documents") or [[]]
        metadatas_list = results.get("metadatas") or [[]]
        distances_list = results.get("distances") or [[]]

        for text, meta, dist in zip(
            documents_list[0],
            metadatas_list[0],
            distances_list[0],
        ):
            output.append({"text": text, "metadata": meta, "distance": dist})

        return output

    def delete_document(self, doc_id: str) -> None:
        if self._fallback_store is not None:
            self._fallback_store.delete_document(doc_id)
            return
        self._chroma_coll.delete(where={"doc_id": {"$eq": doc_id}})

    def collection_count(self) -> int:
        if self._fallback_store is not None:
            return self._fallback_store.collection_count()
        return self._chroma_coll.count()

    def health(self) -> dict[str, Any]:
        if self._fallback_store is not None:
            return self._fallback_store.health()
        try:
            return {"status": "ok", "chunk_count": self._chroma_coll.count(), "backend": "chromadb"}
        except Exception as exc:
            return {"status": "error", "chunk_count": 0, "error": str(exc)}
