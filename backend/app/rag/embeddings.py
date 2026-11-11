"""
Embedding generation for the BankTech RAG knowledge base.
Supports both Google Gemini (text-embedding-004) and OpenAI (text-embedding-3-small).

Security notes
--------------
- The API key is accepted as a plain parameter and must NEVER be logged,
  serialised into a response, or stored anywhere outside server-side memory.
- An empty API key raises ValueError immediately — no network call is made.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException
import httpx

logger = logging.getLogger(__name__)

# =========================================================================== #
# Constants                                                                    #
# =========================================================================== #

GEMINI_EMBED_MODEL: str = "text-embedding-004"
OPENAI_EMBED_MODEL: str = "text-embedding-3-small"
EMBED_TIMEOUT: int = 30   # seconds per API call
EMBED_BATCH_SIZE: int = 100


async def _embed_gemini(texts: list[str], api_key: str) -> list[list[float]]:
    """Generate embeddings using Google Gemini API."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_EMBED_MODEL}:batchEmbedContents"
    all_embeddings: list[list[float]] = []

    for batch_start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[batch_start: batch_start + EMBED_BATCH_SIZE]
        payload = {
            "requests": [
                {
                    "model": f"models/{GEMINI_EMBED_MODEL}",
                    "content": {"parts": [{"text": t or " "}]}
                }
                for t in batch
            ]
        }
        try:
            async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
                res = await client.post(
                    url,
                    json=payload,
                    headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                )
            if res.status_code != 200:
                logger.error("Gemini Embeddings API error: status=%d", res.status_code)
                raise HTTPException(
                    status_code=503,
                    detail=f"Gemini embedding service returned HTTP {res.status_code}. Verify your GEMINI_API_KEY.",
                )
            data = res.json()
            for item in data.get("embeddings", []):
                all_embeddings.append(item["values"])
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Unexpected error calling Gemini embeddings API")
            raise HTTPException(
                status_code=503,
                detail="An unexpected error occurred while generating embeddings with Gemini.",
            ) from exc

    return all_embeddings


async def _embed_openai(texts: list[str], api_key: str) -> list[list[float]]:
    """Generate embeddings using OpenAI API."""
    try:
        import openai as _openai  # noqa: PLC0415
    except ImportError as exc:
        raise HTTPException(
            status_code=501,
            detail="openai package is not installed. Use a GEMINI_API_KEY or install openai.",
        ) from exc

    client = _openai.AsyncOpenAI(api_key=api_key, timeout=EMBED_TIMEOUT)
    all_embeddings: list[list[float]] = []

    for batch_start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[batch_start: batch_start + EMBED_BATCH_SIZE]
        try:
            response = await client.embeddings.create(
                model=OPENAI_EMBED_MODEL,
                input=batch,
            )
            sorted_data: list[Any] = sorted(response.data, key=lambda e: e.index)
            all_embeddings.extend([item.embedding for item in sorted_data])
        except Exception as exc:
            logger.exception("Unexpected error calling OpenAI embeddings API")
            raise HTTPException(
                status_code=503,
                detail="An unexpected error occurred while generating embeddings.",
            ) from exc

    return all_embeddings


# =========================================================================== #
# Public API                                                                   #
# =========================================================================== #


async def get_embeddings(texts: list[str], api_key: str) -> list[list[float]]:
    """Generate embeddings for a list of text strings.
    Automatically detects Gemini key (AIza...) or OpenAI key (sk-...).
    """
    if not api_key or not api_key.strip():
        raise ValueError("API key is required for embedding generation.")

    if not texts:
        return []

    # If it's an OpenAI key (sk-...), use OpenAI client
    if api_key.startswith("sk-"):
        return await _embed_openai(texts, api_key)
    # Default to Google Gemini
    return await _embed_gemini(texts, api_key)


async def get_query_embedding(text: str, api_key: str) -> list[float]:
    """Generate an embedding for a single query string."""
    results = await get_embeddings([text], api_key=api_key)
    if not results:
        raise HTTPException(
            status_code=503,
            detail="Embedding service returned no vectors for the query.",
        )
    return results[0]
