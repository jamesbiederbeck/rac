"""
Client for a text-embedding service used to rank Claims by relevance to a
free-text prompt (see rac.ranking, rac.profile).

This module knows nothing about the RSM — it is a generic HTTP client for
the `/vectors` endpoint of an embeddings-proxy service (POST {"text": ...}
-> {"vector": [floats]}). The default target is the author's homelab
instance; any compatible service can be used by overriding `base_url` or
the RAC_EMBEDDING_URL environment variable.
"""

from __future__ import annotations

import os
from typing import Protocol, Sequence

import httpx

DEFAULT_BASE_URL = "http://chiclets.lan:8081"


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> Sequence[float]:
        """Return the embedding vector for `text`."""


class EmbeddingClient:
    def __init__(self, base_url: str | None = None, timeout: float = 5.0) -> None:
        self.base_url = (base_url or os.environ.get("RAC_EMBEDDING_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout

    def embed(self, text: str) -> tuple[float, ...]:
        response = httpx.post(f"{self.base_url}/vectors", json={"text": text}, timeout=self.timeout)
        response.raise_for_status()
        return tuple(response.json()["vector"])
