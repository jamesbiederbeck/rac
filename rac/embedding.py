"""
Client for a text-embedding service used to rank Claims by relevance to a
free-text prompt (see rac.ranking, rac.profile).

This module knows nothing about the RSM — it is a generic HTTP client for
the `/vectors` endpoint of an embeddings-proxy service (POST {"text": ...}
-> {"vector": [floats]}). There is no default target: a service must be
configured via the RAC_EMBEDDING_URL environment variable or an explicit
`base_url`, since this is an optional integration with no service that
ships with `rac` itself (see embedding_proxy_usage.md).
"""

from __future__ import annotations

import os
from typing import Protocol, Sequence

import httpx


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> Sequence[float]:
        """Return the embedding vector for `text`."""


class EmbeddingNotConfiguredError(RuntimeError):
    """Raised when no embedding service is configured (no base_url and no
    RAC_EMBEDDING_URL). Callers that treat embedding ranking as optional
    should catch this alongside httpx.HTTPError and fall back gracefully."""


class EmbeddingClient:
    def __init__(self, base_url: str | None = None, timeout: float = 5.0) -> None:
        resolved = base_url or os.environ.get("RAC_EMBEDDING_URL")
        if not resolved:
            raise EmbeddingNotConfiguredError(
                "No embedding service configured; set RAC_EMBEDDING_URL or pass base_url explicitly."
            )
        self.base_url = resolved.rstrip("/")
        self.timeout = timeout

    def embed(self, text: str) -> tuple[float, ...]:
        response = httpx.post(f"{self.base_url}/vectors", json={"text": text}, timeout=self.timeout)
        response.raise_for_status()
        return tuple(response.json()["vector"])
