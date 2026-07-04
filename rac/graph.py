"""
ResumeGraph: the assembled, index-backed view of a ResumeDocument.

A ResumeDocument (rac.model) is just a flat bag of entities. ResumeGraph
resolves the id-based relationships described in rsm_spec.md §6 into
lookups and reverse-lookups, and exposes the derived properties from §10.
It performs no validation itself (see rac.validation) beyond what is needed
to build the indices — it assumes the document may be invalid and lets the
validator surface that.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rac.model import (
    Artifact,
    Claim,
    Competency,
    Credential,
    Evidence,
    Organization,
    Person,
    Position,
    ResumeDocument,
)


@dataclass(frozen=True)
class ResumeGraph:
    document: ResumeDocument

    organizations_by_id: dict[str, Organization] = field(default_factory=dict)
    positions_by_id: dict[str, Position] = field(default_factory=dict)
    claims_by_id: dict[str, Claim] = field(default_factory=dict)
    competencies_by_id: dict[str, Competency] = field(default_factory=dict)
    artifacts_by_id: dict[str, Artifact] = field(default_factory=dict)
    evidence_by_id: dict[str, Evidence] = field(default_factory=dict)
    credentials_by_id: dict[str, Credential] = field(default_factory=dict)

    # Reverse indices.
    claims_by_position_id: dict[str, list[Claim]] = field(default_factory=dict)
    person_owned_claims: list[Claim] = field(default_factory=list)
    evidence_by_claim_id: dict[str, list[Evidence]] = field(default_factory=dict)
    positions_by_organization_id: dict[str, list[Position]] = field(default_factory=dict)
    claims_by_competency_id: dict[str, list[Claim]] = field(default_factory=dict)
    artifact_reference_count: dict[str, int] = field(default_factory=dict)

    @property
    def person(self) -> Person:
        return self.document.person

    @classmethod
    def build(cls, document: ResumeDocument) -> "ResumeGraph":
        organizations_by_id = {o.id: o for o in document.organizations}
        positions_by_id = {p.id: p for p in document.positions}
        claims_by_id = {c.id: c for c in document.claims}
        competencies_by_id = {c.id: c for c in document.competencies}
        artifacts_by_id = {a.id: a for a in document.artifacts}
        evidence_by_id = {e.id: e for e in document.evidence}
        credentials_by_id = {c.id: c for c in document.credentials}

        claims_by_position_id: dict[str, list[Claim]] = {}
        person_owned_claims: list[Claim] = []
        for claim in document.claims:
            if claim.position_id is None:
                person_owned_claims.append(claim)
            else:
                claims_by_position_id.setdefault(claim.position_id, []).append(claim)

        evidence_by_claim_id: dict[str, list[Evidence]] = {}
        for ev in document.evidence:
            evidence_by_claim_id.setdefault(ev.claim_id, []).append(ev)

        positions_by_organization_id: dict[str, list[Position]] = {}
        for pos in document.positions:
            positions_by_organization_id.setdefault(pos.organization_id, []).append(pos)

        claims_by_competency_id: dict[str, list[Claim]] = {}
        for claim in document.claims:
            for comp_id in claim.competency_ids:
                claims_by_competency_id.setdefault(comp_id, []).append(claim)

        artifact_reference_count: dict[str, int] = {}
        for claim in document.claims:
            for artifact_id in (*claim.produced_artifact_ids, *claim.referenced_artifact_ids):
                artifact_reference_count[artifact_id] = artifact_reference_count.get(artifact_id, 0) + 1

        return cls(
            document=document,
            organizations_by_id=organizations_by_id,
            positions_by_id=positions_by_id,
            claims_by_id=claims_by_id,
            competencies_by_id=competencies_by_id,
            artifacts_by_id=artifacts_by_id,
            evidence_by_id=evidence_by_id,
            credentials_by_id=credentials_by_id,
            claims_by_position_id=claims_by_position_id,
            person_owned_claims=person_owned_claims,
            evidence_by_claim_id=evidence_by_claim_id,
            positions_by_organization_id=positions_by_organization_id,
            claims_by_competency_id=claims_by_competency_id,
            artifact_reference_count=artifact_reference_count,
        )

    # -- Derived properties (RSM §10) --------------------------------------

    def claim_count_for_competency(self, competency_id: str) -> int:
        return len(self.claims_by_competency_id.get(competency_id, []))

    def reference_count_for_artifact(self, artifact_id: str) -> int:
        return self.artifact_reference_count.get(artifact_id, 0)

    def effective_confidence(self, claim_id: str) -> str | None:
        """Highest of the claim's own confidence and any supporting evidence's."""
        order = ["claimed", "corroborated", "verified"]
        claim = self.claims_by_id.get(claim_id)
        if claim is None:
            return None
        best = claim.confidence.value
        for ev in self.evidence_by_claim_id.get(claim_id, []):
            if order.index(ev.confidence.value) > order.index(best):
                best = ev.confidence.value
        return best
