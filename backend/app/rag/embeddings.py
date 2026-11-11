"""
Embedding generation for the BankTech RAG knowledge base.

Supports Google Gemini (default) and OpenAI (fallback if api_key starts with sk-).
Automatically queries Google ModelService to discover the active embedding model
(text-embedding-004 or embedding-001 across v1beta and v1).
"""

from __future__ import annotations

import logging
from typing import Any
import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

# =========================================================================== #
# Constants                                                                    #
# =========================================================================== #

OPENAI_EMBED_MODEL: str = "text-embedding-3-small"
EMBED_TIMEOUT: int = 30   # seconds per API call
EMBED_BATCH_SIZE: int = 100

_DISCOVERED_EMBED_CONFIG: dict[str, str] = {}


async def _get_gemini_embed_model(api_key: str) -> tuple[str, str]:
    """Find the available embedding model and API version for this API key."""
    if "api_version" in _DISCOVERED_EMBED_CONFIG and "model" in _DISCOVERED_EMBED_CONFIG:
        return _DISCOVERED_EMBED_CONFIG["api_version"], _DISCOVERED_EMBED_CONFIG["model"]

    # Try querying ListModels from Google
    for version in ["v1beta", "v1"]:
        try:
            url = f"https://generativelanguage.googleapis.com/{version}/models"
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.get(url, headers={"x-goog-api-key": api_key})
            if res.status_code == 200:
                data = res.json()
                models = data.get("models", [])
                # Look for preferred embedding models
                for preferred in ["text-embedding-004", "embedding-001"]:
                    for m in models:
                        name = m.get("name", "").replace("models/", "")
                        methods = m.get("supportedGenerationMethods", [])
                        if preferred in name and ("embedContent" in methods or "batchEmbedContents" in methods):
                            _DISCOVERED_EMBED_CONFIG["api_version"] = version
                            _DISCOVERED_EMBED_CONFIG["model"] = name
                            logger.info("Discovered Gemini embedding model: %s (%s)", name, version)
                            return version, name

                # Any model supporting embedContent
                for m in models:
                    methods = m.get("supportedGenerationMethods", [])
                    if "embedContent" in methods:
                        name = m.get("name", "").replace("models/", "")
                        _DISCOVERED_EMBED_CONFIG["api_version"] = version
                        _DISCOVERED_EMBED_CONFIG["model"] = name
                        logger.info("Discovered fallback Gemini embedding model: %s (%s)", name, version)
                        return version, name
        except Exception as exc:
            logger.debug("ListModels check on %s failed: %s", version, exc)

    # Safe default fallback
    return "v1beta", "embedding-001"


async def _embed_gemini(texts: list[str], api_key: str) -> list[list[float]]:
    """Generate embeddings using Google Gemini API."""
    version, model = await _get_gemini_embed_model(api_key)

    # 1. Try batchEmbedContents
    batch_url = f"https://generativelanguage.googleapis.com/{version}/models/{model}:batchEmbedContents"
    all_embeddings: list[list[float]] = []
    batch_success = True

    for batch_start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[batch_start: batch_start + EMBED_BATCH_SIZE]
        payload = {
            "requests": [
                {
                    "model": f"models/{model}",
                    "content": {"parts": [{"text": t or " "}]}
                }
                for t in batch
            ]
        }
        try:
            async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
                res = await client.post(
                    batch_url,
                    json=payload,
                    headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                )
            if res.status_code == 200:
                data = res.json()
                for item in data.get("embeddings", []):
                    if isinstance(item, dict):
                        if "values" in item:
                            all_embeddings.append(item["values"])
                        elif "embedding" in item and isinstance(item["embedding"], dict):
                            all_embeddings.append(item["embedding"].get("values", []))
            else:
                batch_success = False
                break
        except Exception:
            batch_success = False
            break

    if batch_success and len(all_embeddings) == len(texts):
        return all_embeddings

    # 2. Fallback: single embedContent per text
    all_embeddings = []
    single_url = f"https://generativelanguage.googleapis.com/{version}/models/{model}:embedContent"

    for text in texts:
        payload = {
            "model": f"models/{model}",
            "content": {"parts": [{"text": text or " "}]}
        }
        try:
            async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
                res = await client.post(
                    single_url,
                    json=payload,
                    headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                )
            if res.status_code == 200:
                data = res.json()
                emb = data.get("embedding", {}).get("values", [])
                if not emb:
                    raise HTTPException(status_code=503, detail="Gemini returned empty embedding vector.")
                all_embeddings.append(emb)
            else:
                err_msg = ""
                try:
                    err_msg = res.json().get("error", {}).get("message", res.text[:200])
                except Exception:
                    err_msg = res.text[:200]
                raise HTTPException(
                    status_code=503,
                    detail=f"Gemini embedContent error ({res.status_code}): {err_msg} (Model: {model}, Version: {version})",
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Unexpected error calling Gemini embedContent API")
            raise HTTPException(
                status_code=503,
                detail=f"An unexpected error occurred while generating embeddings with Gemini: {exc}",
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
    Automatically detects Gemini key or OpenAI key (sk-...).
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
    """Generate a single embedding vector for a query string."""
    results = await get_embeddings([text], api_key)
    if not results:
        raise ValueError("Embedding generation produced no results.")
    return results[0]
