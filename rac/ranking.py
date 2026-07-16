"""
Rank Claims by semantic similarity to a free-text query, using an
EmbeddingProvider (rac.embedding). This is the "promptable" ranking
mechanism consumed by rac.profile.apply_profile.
"""

from __future__ import annotations

import math
from typing import Sequence

from rac.embedding import EmbeddingProvider
from rac.model import Claim


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def rank_claims_by_query(
    claims: Sequence[Claim], query: str, provider: EmbeddingProvider
) -> list[tuple[Claim, float]]:
    """Score each claim by cosine similarity of its text to `query`.

    Claim text is embedded once per distinct value (two claims with
    identical text share one embedding call) since the RSM places no
    uniqueness constraint on Claim.text.
    """
    query_vector = provider.embed(query)

    text_vectors: dict[str, Sequence[float]] = {}
    for claim in claims:
        if claim.text not in text_vectors:
            text_vectors[claim.text] = provider.embed(claim.text)

    scored = [(claim, cosine_similarity(query_vector, text_vectors[claim.text])) for claim in claims]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored
