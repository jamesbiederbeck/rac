"""
Build Profile: the filtering/weighting configuration described in
project_plan.md's "Build Profiles" section. A profile selects which Claims
are in scope for a given resume build and how they should be ordered — it
never modifies the RSM itself (rsm_spec.md draws this boundary at the
Build Profile stage, see rsm_spec.md §14).

`theme` and `page_limit` are accepted here (part of the project_plan.md
schema) but unused: no renderer exists yet to consume them.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from rac.embedding import EmbeddingProvider
from rac.graph import ResumeGraph
from rac.model import Claim, Importance
from rac.ranking import rank_claims_by_query


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

_IMPORTANCE_SCORE = {
    Importance.LOW: 1.0,
    Importance.MEDIUM: 2.0,
    Importance.HIGH: 3.0,
    Importance.CRITICAL: 4.0,
}


class ProfileFilters(_Frozen):
    include_tags: tuple[str, ...] = ()
    exclude_tags: tuple[str, ...] = ()


class BuildProfile(_Frozen):
    name: str
    theme: str | None = None
    page_limit: int | None = None
    filters: ProfileFilters = ProfileFilters()
    weights: dict[str, float] = {}

    # Free-text prompt (e.g. a target job description) used to rank Claims
    # by embedding similarity — see rac.ranking.rank_claims_by_query.
    query: str | None = None


def load_build_profile(path: Path) -> BuildProfile:
    raw = yaml.safe_load(path.read_text()) or {}
    return BuildProfile.model_validate(raw)


def filter_claims(graph: ResumeGraph, profile: BuildProfile) -> list[Claim]:
    include = {t.lower() for t in profile.filters.include_tags}
    exclude = {t.lower() for t in profile.filters.exclude_tags}

    selected = []
    for claim in graph.document.claims:
        tags = {t.lower() for t in claim.tags}
        if include and not (tags & include):
            continue
        if exclude and (tags & exclude):
            continue
        selected.append(claim)
    return selected


def score_by_weights(graph: ResumeGraph, claim: Claim, profile: BuildProfile) -> float:
    """Fallback/secondary score: Claim.importance scaled by the average of
    any matching competency weights (case-insensitive match on
    Competency.name). A claim with no competencies, or none matching a
    configured weight, scores at the neutral multiplier of 1.0."""
    weights = {name.lower(): value for name, value in profile.weights.items()}

    if not claim.competency_ids:
        multiplier = 1.0
    else:
        matched = [
            weights.get(graph.competencies_by_id[comp_id].name.lower(), 1.0)
            for comp_id in claim.competency_ids
            if comp_id in graph.competencies_by_id
        ]
        multiplier = (sum(matched) / len(matched)) if matched else 1.0

    return _IMPORTANCE_SCORE[claim.importance] * multiplier


def apply_profile(
    graph: ResumeGraph, profile: BuildProfile, provider: EmbeddingProvider | None = None
) -> list[tuple[Claim, float]]:
    """Filter Claims per `profile.filters`, then rank the survivors.

    When `profile.query` and an EmbeddingProvider are both supplied,
    ranking is driven by embedding similarity to the query, with
    `score_by_weights` applied as a secondary multiplier so configured
    competency weights still bias the order. Otherwise, ranking falls back
    to `score_by_weights` alone.
    """
    claims = filter_claims(graph, profile)

    if profile.query and provider is not None:
        similarity_ranked = rank_claims_by_query(claims, profile.query, provider)
        scored = [
            (claim, similarity * score_by_weights(graph, claim, profile))
            for claim, similarity in similarity_ranked
        ]
    else:
        scored = [(claim, score_by_weights(graph, claim, profile)) for claim in claims]

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored
