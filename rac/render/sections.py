"""
Format-independent intermediate representation for rendering a resume.

Per rsm_spec.md §14, rendering is a projection of the model: section
presence/ordering is derived by grouping over typed relationships, never
stored on the RSM itself (Position -> Claim gives Experience, Claim ->
Competency gives Skills, Claim -> Artifact gives Projects, Person ->
Credential gives Education/Certifications). This module builds that
projection once; rac.render.markdown/html/pdf each consume it without
knowing anything about the underlying graph.

Claim *selection* (which claims are eligible to render at all -- profile
filtering, visibility) is a policy decision made by the caller (rac.cli);
this module only groups/orders whatever claims it is given.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from rac.graph import ResumeGraph
from rac.model import Artifact, Claim, Competency, Credential, Organization, Person, Position


@dataclass(frozen=True)
class ExperienceEntry:
    position: Position
    organization: Organization | None
    claims: tuple[Claim, ...]


@dataclass(frozen=True)
class ProjectEntry:
    artifact: Artifact
    produced_by: tuple[Claim, ...]
    referenced_by: tuple[Claim, ...]


@dataclass(frozen=True)
class CredentialEntry:
    credential: Credential
    organization: Organization | None


@dataclass(frozen=True)
class ResumeSections:
    person: Person
    experience: tuple[ExperienceEntry, ...] = ()
    independent_claims: tuple[Claim, ...] = ()
    competencies: tuple[Competency, ...] = ()
    projects: tuple[ProjectEntry, ...] = ()
    credentials: tuple[CredentialEntry, ...] = ()


def _position_sort_key(position: Position) -> tuple[date, date]:
    """Most-recent-first: open-ended (ongoing) positions sort before any
    position with a real end date, ties broken by start date descending."""
    end = position.interval.end or date.max
    return (end, position.interval.start)


def _credential_sort_key(credential: Credential) -> date:
    return credential.issue_date or date.min


def build_resume_sections(graph: ResumeGraph, claims: "list[Claim] | tuple[Claim, ...]") -> ResumeSections:
    claims_by_position: dict[str, list[Claim]] = {}
    independent_claims: list[Claim] = []
    for claim in claims:
        if claim.position_id is None:
            independent_claims.append(claim)
        else:
            claims_by_position.setdefault(claim.position_id, []).append(claim)

    experience = [
        ExperienceEntry(
            position=position,
            organization=graph.organizations_by_id.get(position.organization_id),
            claims=tuple(claims_by_position[position.id]),
        )
        for position in sorted(graph.document.positions, key=_position_sort_key, reverse=True)
        if position.id in claims_by_position
    ]

    competency_ids: set[str] = set()
    produced: dict[str, list[Claim]] = {}
    referenced: dict[str, list[Claim]] = {}
    for claim in claims:
        competency_ids.update(claim.competency_ids)
        for artifact_id in claim.produced_artifact_ids:
            produced.setdefault(artifact_id, []).append(claim)
        for artifact_id in claim.referenced_artifact_ids:
            referenced.setdefault(artifact_id, []).append(claim)

    competencies = sorted(
        (graph.competencies_by_id[cid] for cid in competency_ids if cid in graph.competencies_by_id),
        key=lambda c: (-graph.claim_count_for_competency(c.id), c.name),
    )

    artifact_ids = set(produced) | set(referenced)
    projects = [
        ProjectEntry(
            artifact=graph.artifacts_by_id[aid],
            produced_by=tuple(produced.get(aid, [])),
            referenced_by=tuple(referenced.get(aid, [])),
        )
        for aid in artifact_ids
        if aid in graph.artifacts_by_id
    ]
    projects.sort(key=lambda p: p.artifact.name)

    credentials = [
        CredentialEntry(
            credential=credential,
            organization=graph.organizations_by_id.get(credential.organization_id),
        )
        for credential in sorted(graph.document.credentials, key=_credential_sort_key, reverse=True)
    ]

    return ResumeSections(
        person=graph.person,
        experience=tuple(experience),
        independent_claims=tuple(independent_claims),
        competencies=tuple(competencies),
        projects=tuple(projects),
        credentials=tuple(credentials),
    )
