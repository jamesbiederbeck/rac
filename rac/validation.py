"""
Graph-level validation of a ResumeGraph against rsm_spec.md.

Pydantic (rac.model) already enforces per-entity field validation and
invariants that are local to a single entity (non-empty text, date
ordering, produced/referenced disjointness, ...). This module covers
everything that requires seeing the *whole graph*: referential integrity,
cardinality, closed-world constraints, and the specific invariants called
out in §4 and §8 of the spec.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from rac.graph import ResumeGraph
from rac.model import EmploymentType


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Issue:
    severity: Severity
    code: str
    message: str
    entity_id: str | None = None

    def __str__(self) -> str:
        loc = f" [{self.entity_id}]" if self.entity_id else ""
        return f"{self.severity.value.upper()}{loc}: {self.message} ({self.code})"


def validate(graph: ResumeGraph) -> list[Issue]:
    issues: list[Issue] = []
    _check_unique_ids(graph, issues)
    _check_referential_integrity(graph, issues)
    _check_position_invariants(graph, issues)
    _check_position_overlap(graph, issues)
    _check_competency_normalization(graph, issues)
    _check_organization_dedup(graph, issues)
    _check_artifact_orphans(graph, issues)
    _check_claim_bare_assertions(graph, issues)
    _check_person_has_positions(graph, issues)
    return issues


# ---------------------------------------------------------------------------
# Identity (RSM §3.1, §8.3): every entity id must be unique across the
# entire RSM instance, not merely within its own type's collection. A
# collision silently drops data in any dict-keyed index (last write wins),
# so this must be checked before any index-based check is trusted.
# ---------------------------------------------------------------------------


def _check_unique_ids(graph: ResumeGraph, issues: list[Issue]) -> None:
    doc = graph.document
    all_entities = [
        ("Person", doc.person),
        *(("Organization", o) for o in doc.organizations),
        *(("Position", p) for p in doc.positions),
        *(("Claim", c) for c in doc.claims),
        *(("Competency", c) for c in doc.competencies),
        *(("Artifact", a) for a in doc.artifacts),
        *(("Evidence", e) for e in doc.evidence),
        *(("Credential", c) for c in doc.credentials),
    ]
    seen: dict[str, str] = {}
    for kind, entity in all_entities:
        if entity.id in seen:
            issues.append(
                Issue(
                    Severity.ERROR,
                    "duplicate-entity-id",
                    f"{kind} id {entity.id!r} is already used by a {seen[entity.id]} "
                    "entity; ids must be globally unique within the RSM instance",
                    entity.id,
                )
            )
        else:
            seen[entity.id] = kind


# ---------------------------------------------------------------------------
# Referential integrity (RSM §8.3): every ref(Entity) must resolve.
# ---------------------------------------------------------------------------


def _check_referential_integrity(graph: ResumeGraph, issues: list[Issue]) -> None:
    doc = graph.document

    for pos in doc.positions:
        if pos.organization_id not in graph.organizations_by_id:
            issues.append(
                Issue(
                    Severity.ERROR,
                    "dangling-reference",
                    f"Position references unknown Organization {pos.organization_id!r}",
                    pos.id,
                )
            )

    for claim in doc.claims:
        if claim.position_id is not None and claim.position_id not in graph.positions_by_id:
            issues.append(
                Issue(
                    Severity.ERROR,
                    "dangling-reference",
                    f"Claim references unknown Position {claim.position_id!r}",
                    claim.id,
                )
            )
        for comp_id in claim.competency_ids:
            if comp_id not in graph.competencies_by_id:
                issues.append(
                    Issue(
                        Severity.ERROR,
                        "dangling-reference",
                        f"Claim references unknown Competency {comp_id!r}",
                        claim.id,
                    )
                )
        for art_id in (*claim.produced_artifact_ids, *claim.referenced_artifact_ids):
            if art_id not in graph.artifacts_by_id:
                issues.append(
                    Issue(
                        Severity.ERROR,
                        "dangling-reference",
                        f"Claim references unknown Artifact {art_id!r}",
                        claim.id,
                    )
                )

    for ev in doc.evidence:
        if ev.claim_id not in graph.claims_by_id:
            issues.append(
                Issue(
                    Severity.ERROR,
                    "dangling-reference",
                    f"Evidence references unknown Claim {ev.claim_id!r}",
                    ev.id,
                )
            )

    for cred in doc.credentials:
        if cred.organization_id not in graph.organizations_by_id:
            issues.append(
                Issue(
                    Severity.ERROR,
                    "dangling-reference",
                    f"Credential references unknown issuing Organization {cred.organization_id!r}",
                    cred.id,
                )
            )
        for comp_id in cred.competency_ids:
            if comp_id not in graph.competencies_by_id:
                issues.append(
                    Issue(
                        Severity.ERROR,
                        "dangling-reference",
                        f"Credential references unknown Competency {comp_id!r}",
                        cred.id,
                    )
                )


# ---------------------------------------------------------------------------
# Position invariants (RSM §4.3): at most one open-ended position.
# ---------------------------------------------------------------------------


def _check_position_invariants(graph: ResumeGraph, issues: list[Issue]) -> None:
    open_ended = [p for p in graph.document.positions if p.interval.is_open_ended]
    if len(open_ended) > 1:
        for pos in open_ended:
            issues.append(
                Issue(
                    Severity.ERROR,
                    "multiple-open-ended-positions",
                    "More than one Position has an open-ended interval "
                    "(no end date); at most one is permitted",
                    pos.id,
                )
            )


# ---------------------------------------------------------------------------
# Overlap validation (RSM §4.3): warning in general, error for two
# overlapping full-time positions at different organizations.
# ---------------------------------------------------------------------------


def _intervals_overlap(a, b) -> bool:
    a_end = a.end or date_max()
    b_end = b.end or date_max()
    return a.start <= b_end and b.start <= a_end


def date_max():
    from datetime import date

    return date.max


def _check_position_overlap(graph: ResumeGraph, issues: list[Issue]) -> None:
    positions = list(graph.document.positions)
    for i, a in enumerate(positions):
        for b in positions[i + 1 :]:
            if not _intervals_overlap(a.interval, b.interval):
                continue
            if (
                a.employment_type == EmploymentType.FULL_TIME
                and b.employment_type == EmploymentType.FULL_TIME
                and a.organization_id != b.organization_id
            ):
                issues.append(
                    Issue(
                        Severity.ERROR,
                        "overlapping-full-time-positions",
                        f"Position {a.id!r} and {b.id!r} are both full-time at "
                        "different organizations but overlap in time",
                        a.id,
                    )
                )
            else:
                issues.append(
                    Issue(
                        Severity.WARNING,
                        "overlapping-positions",
                        f"Position {a.id!r} and {b.id!r} overlap in time",
                        a.id,
                    )
                )


# ---------------------------------------------------------------------------
# Competency normalization (RSM §4.5, §9.1).
# ---------------------------------------------------------------------------


def _check_competency_normalization(graph: ResumeGraph, issues: list[Issue]) -> None:
    seen_names: dict[str, str] = {}
    all_names_and_aliases: dict[str, str] = {}

    for comp in graph.document.competencies:
        key = comp.name.strip().lower()
        if key in seen_names:
            issues.append(
                Issue(
                    Severity.ERROR,
                    "duplicate-competency-name",
                    f"Competency name {comp.name!r} duplicates {seen_names[key]!r}",
                    comp.id,
                )
            )
        else:
            seen_names[key] = comp.id
        all_names_and_aliases.setdefault(key, comp.id)

    for comp in graph.document.competencies:
        for alias in comp.aliases:
            key = alias.strip().lower()
            owner = all_names_and_aliases.get(key)
            if owner is not None and owner != comp.id:
                issues.append(
                    Issue(
                        Severity.ERROR,
                        "ambiguous-competency-alias",
                        f"Alias {alias!r} on Competency {comp.id!r} collides with "
                        f"Competency {owner!r}",
                        comp.id,
                    )
                )


# ---------------------------------------------------------------------------
# Organization deduplication (RSM §9.3) — warning, not error.
# ---------------------------------------------------------------------------


def _check_organization_dedup(graph: ResumeGraph, issues: list[Issue]) -> None:
    seen: dict[tuple[str, str], str] = {}
    for org in graph.document.organizations:
        key = (org.name.strip().lower(), org.type.value)
        if key in seen:
            issues.append(
                Issue(
                    Severity.WARNING,
                    "duplicate-organization",
                    f"Organization {org.name!r} ({org.type.value}) duplicates {seen[key]!r}",
                    org.id,
                )
            )
        else:
            seen[key] = org.id


# ---------------------------------------------------------------------------
# Artifact orphans (RSM §4.6) — warning.
# ---------------------------------------------------------------------------


def _check_artifact_orphans(graph: ResumeGraph, issues: list[Issue]) -> None:
    for artifact in graph.document.artifacts:
        if graph.reference_count_for_artifact(artifact.id) == 0:
            issues.append(
                Issue(
                    Severity.WARNING,
                    "orphaned-artifact",
                    f"Artifact {artifact.name!r} is not PRODUCED or REFERENCES'd by any Claim",
                    artifact.id,
                )
            )


# ---------------------------------------------------------------------------
# Bare-assertion claims (RSM §4.4) — warning.
# ---------------------------------------------------------------------------


def _check_person_has_positions(graph: ResumeGraph, issues: list[Issue]) -> None:
    """RSM §6 pins `Person HELD Position` at 1..*. A freshly-created resume
    (e.g. `rac init`) has zero Positions, which is legitimate in-progress
    state, not corrupt data — so this is a warning, not an error."""
    if not graph.document.positions:
        issues.append(
            Issue(
                Severity.WARNING,
                "person-has-no-positions",
                "Person has no Positions; the RSM spec expects at least one "
                "(§6) once the resume is complete",
                graph.person.id,
            )
        )


def _check_claim_bare_assertions(graph: ResumeGraph, issues: list[Issue]) -> None:
    for claim in graph.document.claims:
        if (
            not claim.competency_ids
            and not claim.produced_artifact_ids
            and not claim.referenced_artifact_ids
            and not graph.evidence_by_claim_id.get(claim.id)
        ):
            issues.append(
                Issue(
                    Severity.WARNING,
                    "unsupported-unclassified-claim",
                    "Claim demonstrates no competencies, references no artifacts, "
                    "and has no supporting evidence",
                    claim.id,
                )
            )
