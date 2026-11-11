"""
OpenAI embedding generation for the BankTech RAG knowledge base.

openai is an optional dependency imported lazily; the server starts without it
and raises a clear error only when embeddings are actually requested.

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

logger = logging.getLogger(__name__)

# =========================================================================== #
# Constants                                                                    #
# =========================================================================== #

EMBED_MODEL: str = "text-embedding-3-small"
EMBED_TIMEOUT: int = 30   # seconds per API call
EMBED_BATCH_SIZE: int = 100  # texts per OpenAI request


# =========================================================================== #
# Public API                                                                   #
# =========================================================================== #


async def get_embeddings(texts: list[str], api_key: str) -> list[list[float]]:
    """Generate embeddings for a list of text strings.

    Parameters
    ----------
    texts:
        Input strings to embed. Empty strings are accepted; the API will return
        a zero-ish vector for them.
    api_key:
        OpenAI secret key. Must be non-empty; must NEVER be logged.

    Returns
    -------
    list[list[float]]
        One embedding vector per input text, in the same order.

    Raises
    ------
    ValueError
        When *api_key* is empty or blank.
    ImportError
        When the ``openai`` package is not installed.
    HTTPException(503)
        When the OpenAI API returns an error.
    """
    if not api_key or not api_key.strip():
        raise ValueError("OpenAI API key is required for embedding generation.")

    try:
        import openai as _openai  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "openai is required for embedding generation but is not installed. "
            "Install it with:  pip install openai"
        ) from exc

    if not texts:
        return []

    client = _openai.AsyncOpenAI(api_key=api_key, timeout=EMBED_TIMEOUT)
    all_embeddings: list[list[float]] = []

    # Process in batches to stay within OpenAI token / item limits.
    for batch_start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[batch_start: batch_start + EMBED_BATCH_SIZE]
        try:
            response = await client.embeddings.create(
                model=EMBED_MODEL,
                input=batch,
            )
        except _openai.OpenAIError as exc:
            logger.error(
                "OpenAI embeddings API error (batch starting at %d): %s",
                batch_start,
                type(exc).__name__,  # log type, NOT exc details which may echo key
            )
            raise HTTPException(
                status_code=503,
                detail=(
                    "The embedding service is temporarily unavailable. "
                    "Please try again later."
                ),
            ) from exc
        except Exception as exc:
            logger.exception("Unexpected error calling OpenAI embeddings API")
            raise HTTPException(
                status_code=503,
                detail="An unexpected error occurred while generating embeddings.",
            ) from exc

        # OpenAI returns embeddings sorted by index; preserve that order.
        sorted_data: list[Any] = sorted(response.data, key=lambda e: e.index)
        all_embeddings.extend([item.embedding for item in sorted_data])

    return all_embeddings


async def get_query_embedding(text: str, api_key: str) -> list[float]:
    """Generate an embedding for a single query string.

    Parameters
    ----------
    text:
        The query to embed.
    api_key:
        OpenAI secret key (server-side only, never logged or returned).

    Returns
    -------
    list[float]
        A single embedding vector.
    """
    results = await get_embeddings([text], api_key=api_key)
    if not results:
        raise HTTPException(
            status_code=503,
            detail="Embedding service returned no vectors for the query.",
        )
    return results[0]
