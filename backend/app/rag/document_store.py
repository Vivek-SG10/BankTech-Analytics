"""
ChromaDB vector store wrapper for the BankTech RAG knowledge base.

chromadb is an optional dependency — it is imported lazily so the rest of the
application can start without it and surface a clear error only when this
module is actually used.

Access-level filtering
----------------------
Stored chunks carry an ``access_level`` metadata field:
  - "all"   → visible to every role including customer
  - "staff" → visible to employee, manager, researcher, admin
  - "admin" → visible to admin only

The ``query`` method maps the caller's resolved access tier to the set of
document access levels it may read and constructs a ChromaDB ``$in`` filter.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Access-level visibility map: caller tier → allowed doc access_levels
_ACCESS_TIER_MAP: dict[str, list[str]] = {
    "all": ["all"],
    "staff": ["all", "staff"],
    "admin": ["all", "staff", "admin"],
}


class VectorStore:
    """Thin wrapper around a ChromaDB persistent collection."""

    # ------------------------------------------------------------------ #
    # Construction                                                         #
    # ------------------------------------------------------------------ #

    def __init__(
        self,
        persist_directory: str,
        collection_name: str = "banktech_kb",
    ) -> None:
        """Initialise the persistent ChromaDB client and obtain/create the collection.

        Parameters
        ----------
        persist_directory:
            Filesystem path where ChromaDB persists its data.
        collection_name:
            Name of the ChromaDB collection to use.

        Raises
        ------
        ImportError
            When *chromadb* is not installed in the current environment.
        """
        try:
            import chromadb  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "chromadb is required for the vector store but is not installed. "
                "Install it with:  pip install chromadb"
            ) from exc

        self._collection_name = collection_name
        self._client = chromadb.PersistentClient(path=persist_directory)

        # Cosine distance is used throughout; distance 0 = identical vectors,
        # distance 2 = perfectly opposite.
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "VectorStore initialised: collection=%r persist_dir=%r",
            collection_name,
            persist_directory,
        )

    # ------------------------------------------------------------------ #
    # Write operations                                                     #
    # ------------------------------------------------------------------ #

    def add_chunks(self, chunks: list[dict[str, Any]]) -> None:
        """Upsert text chunks into the collection.

        Parameters
        ----------
        chunks:
            Each element must contain:
            - ``id``            (str) — unique chunk identifier
            - ``text``          (str) — the chunk's text content
            - ``embedding``     (list[float], optional) — pre-computed vector;
                                when provided it is passed directly to ChromaDB
                                so no secondary embedding function is needed.
            - ``metadata``      (dict) — must include at minimum:
                - doc_id        (str)
                - title         (str)
                - page_or_section (str | None)
                - file_type     (str)
                - access_level  (str)
                - chunk_index   (int)
        """
        if not chunks:
            return

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []
        embeddings: list[list[float]] | None = None

        # Collect pre-computed embeddings only when ALL chunks carry them.
        # Mixed batches fall back to ChromaDB's default embedding function.
        all_have_embeddings = all("embedding" in c for c in chunks)
        if all_have_embeddings:
            embeddings = []

        for chunk in chunks:
            ids.append(chunk["id"])
            documents.append(chunk["text"])
            # ChromaDB metadata values must be str | int | float | bool.
            # Coerce None → empty string so the filter layer stays simple.
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

        self._collection.upsert(**upsert_kwargs)
        logger.debug("Upserted %d chunks into collection %r", len(chunks), self._collection_name)

    # ------------------------------------------------------------------ #
    # Query                                                                #
    # ------------------------------------------------------------------ #

    def query(
        self,
        query_embedding: list[float],
        top_k: int,
        access_level_filter: str,
    ) -> list[dict[str, Any]]:
        """Retrieve the most similar chunks that the caller is allowed to see.

        Parameters
        ----------
        query_embedding:
            Pre-computed embedding vector for the user's question.
        top_k:
            Maximum number of results to return.
        access_level_filter:
            One of "all" | "staff" | "admin" (resolved by the API layer from
            the authenticated user's role).

        Returns
        -------
        list[dict]
            Each dict has keys: ``text``, ``metadata``, ``distance``.
        """
        allowed_levels = _ACCESS_TIER_MAP.get(access_level_filter, ["all"])

        where_clause: dict[str, Any]
        if len(allowed_levels) == 1:
            where_clause = {"access_level": {"$eq": allowed_levels[0]}}
        else:
            where_clause = {"access_level": {"$in": allowed_levels}}

        try:
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_clause,
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            logger.exception("ChromaDB query failed")
            raise

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

    # ------------------------------------------------------------------ #
    # Delete                                                               #
    # ------------------------------------------------------------------ #

    def delete_document(self, doc_id: str) -> None:
        """Remove all chunks associated with *doc_id* from the collection.

        Parameters
        ----------
        doc_id:
            The document UUID whose chunks should be purged.
        """
        try:
            self._collection.delete(where={"doc_id": {"$eq": doc_id}})
            logger.info("Deleted chunks for doc_id=%r from collection %r", doc_id, self._collection_name)
        except Exception:
            logger.exception("Failed to delete chunks for doc_id=%r", doc_id)
            raise

    # ------------------------------------------------------------------ #
    # Introspection                                                        #
    # ------------------------------------------------------------------ #

    def collection_count(self) -> int:
        """Return the total number of chunks currently stored."""
        return self._collection.count()

    def health(self) -> dict[str, Any]:
        """Return a simple health dict for the /health endpoint."""
        try:
            count = self.collection_count()
            return {"status": "ok", "chunk_count": count}
        except Exception as exc:  # noqa: BLE001
            logger.warning("VectorStore health check failed: %s", exc)
            return {"status": "error", "chunk_count": 0, "error": str(exc)}
