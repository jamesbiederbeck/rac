"""
Merge engine: turns an ExtractedResume (rac.ingest.extracted -- flat, id-less
facts from either the OpenAI-compatible extractor or the ingest-resume
skill) into a real ResumeDocument, reusing existing entities wherever
possible instead of creating near-duplicates every time a resume gets
reworded across versions.

Builds a *new* ResumeDocument (frozen, per the RSM's immutable-per-build
convention -- rac/model.py) rather than mutating the existing one.

Nothing here decides silently when a match is uncertain: ambiguous or
lower-confidence matches are still resolved one way (see thresholds below)
but always recorded in the returned IngestReport, on the same "reviewable
as a diff" principle project_plan.md's AI Layer describes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from rac.embedding import EmbeddingProvider
from rac.ingest.extracted import ExtractedClaim, ExtractedCredential, ExtractedEvidence, ExtractedPosition, ExtractedResume
from rac.model import (
    Artifact,
    Claim,
    Competency,
    ConfidenceLevel,
    Credential,
    CredentialType,
    DateOrInterval,
    EmploymentType,
    Evidence,
    EvidenceType,
    Importance,
    Metric,
    MetricDirection,
    Organization,
    OrganizationType,
    Person,
    Position,
    ResumeDocument,
    Visibility,
)
from rac.ranking import cosine_similarity

_CLAIM_DUPLICATE_THRESHOLD = 0.90
_CLAIM_POSSIBLE_DUPLICATE_THRESHOLD = 0.75
_POSITION_TITLE_MATCH_THRESHOLD = 0.85
_POSITION_ADJACENCY_DAYS = 45


@dataclass
class IngestReport:
    added_organizations: list[str] = field(default_factory=list)
    added_positions: list[str] = field(default_factory=list)
    added_claims: list[str] = field(default_factory=list)
    added_competencies: list[str] = field(default_factory=list)
    added_credentials: list[str] = field(default_factory=list)
    skipped_duplicate_claims: list[tuple[str, str, float]] = field(default_factory=list)
    possible_duplicate_claims: list[tuple[str, str, float]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "x"


def _unique_id(prefix: str, seed: str, used_ids: set[str]) -> str:
    base = f"{prefix}_{_slugify(seed)}"
    candidate = base
    n = 2
    while candidate in used_ids:
        candidate = f"{base}_{n}"
        n += 1
    used_ids.add(candidate)
    return candidate


def _coerce_enum(enum_cls, value: str | None, default):
    if value is None:
        return default
    try:
        return enum_cls(value)
    except ValueError:
        return default


def _parse_flexible_date(value: str) -> date:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Could not parse date {value!r}; expected YYYY-MM-DD, YYYY-MM, or YYYY")


def _interval_close_enough(a: DateOrInterval, b: DateOrInterval) -> bool:
    a_end = a.end or date.max
    b_end = b.end or date.max
    if a.start <= b_end and b.start <= a_end:
        return True
    if a_end == date.max or b_end == date.max:
        return False
    gap = (b.start - a_end).days if b.start > a_end else (a.start - b_end).days
    return 0 <= gap <= _POSITION_ADJACENCY_DAYS


def _titles_match(a: str, b: str, embedding_provider: EmbeddingProvider | None) -> bool:
    a_norm, b_norm = a.strip().lower(), b.strip().lower()
    if a_norm == b_norm:
        return True
    if embedding_provider is None:
        return False
    score = cosine_similarity(embedding_provider.embed(a), embedding_provider.embed(b))
    return score >= _POSITION_TITLE_MATCH_THRESHOLD


def _resolve_organization(
    name: str,
    org_type_hint: str | None,
    organizations: list[Organization],
    org_index: dict[tuple[str, str], str],
    used_ids: set[str],
    report: IngestReport,
) -> str:
    org_type = _coerce_enum(OrganizationType, org_type_hint, OrganizationType.EMPLOYER)
    name_key = name.strip().lower()

    key = (name_key, org_type.value)
    if key in org_index:
        return org_index[key]
    # org_type is only ever a best guess from extraction; fall back to a
    # name-only match across types rather than creating a near-duplicate
    # Organization just because the guessed type didn't match.
    for (existing_name, _existing_type), existing_id in org_index.items():
        if existing_name == name_key:
            return existing_id

    new_id = _unique_id("org", name, used_ids)
    organizations.append(Organization(id=new_id, name=name.strip(), type=org_type))
    org_index[key] = new_id
    report.added_organizations.append(new_id)
    return new_id


def _resolve_position(
    extracted_pos: ExtractedPosition,
    org_id: str,
    positions: list[Position],
    used_ids: set[str],
    embedding_provider: EmbeddingProvider | None,
    report: IngestReport,
) -> str:
    start = _parse_flexible_date(extracted_pos.start_date)
    end = _parse_flexible_date(extracted_pos.end_date) if extracted_pos.end_date else None
    interval = DateOrInterval(start=start, end=end)
    employment_type = _coerce_enum(EmploymentType, extracted_pos.employment_type, EmploymentType.FULL_TIME)

    for pos in positions:
        if pos.organization_id != org_id:
            continue
        if not _interval_close_enough(pos.interval, interval):
            continue
        if not _titles_match(pos.title, extracted_pos.title, embedding_provider):
            continue
        if pos.interval.start != start or pos.interval.end != end:
            report.notes.append(
                f"Position {pos.id!r} matched extracted '{extracted_pos.title}' but dates differ "
                f"(existing {pos.interval.start}–{pos.interval.end or 'present'} vs extracted "
                f"{start}–{end or 'present'}); left unchanged, review manually."
            )
        return pos.id

    new_id = _unique_id("pos", f"{extracted_pos.title}_{extracted_pos.organization_name}", used_ids)
    positions.append(
        Position(
            id=new_id,
            title=extracted_pos.title.strip(),
            employment_type=employment_type,
            interval=interval,
            organization_id=org_id,
        )
    )
    report.added_positions.append(new_id)
    return new_id


def _resolve_competency(
    name: str,
    competencies: list[Competency],
    competency_index: dict[str, str],
    used_ids: set[str],
    report: IngestReport,
) -> str:
    key = name.strip().lower()
    if key in competency_index:
        return competency_index[key]
    new_id = _unique_id("comp", name, used_ids)
    competencies.append(Competency(id=new_id, name=name.strip()))
    competency_index[key] = new_id
    report.added_competencies.append(new_id)
    return new_id


def _resolve_claim(
    extracted_claim: ExtractedClaim,
    container_claims: list[Claim],
    position_id: str | None,
    competencies: list[Competency],
    competency_index: dict[str, str],
    used_ids: set[str],
    embedding_provider: EmbeddingProvider | None,
    report: IngestReport,
) -> Claim | None:
    text_norm = " ".join(extracted_claim.text.split()).strip()

    for existing in container_claims:
        if " ".join(existing.text.split()).strip().lower() == text_norm.lower():
            report.skipped_duplicate_claims.append((text_norm, existing.id, 1.0))
            return None

    best_match: Claim | None = None
    best_score = 0.0
    if embedding_provider is not None and container_claims:
        new_vector = embedding_provider.embed(text_norm)
        for existing in container_claims:
            score = cosine_similarity(new_vector, embedding_provider.embed(existing.text))
            if score > best_score:
                best_score, best_match = score, existing

    if best_match is not None and best_score >= _CLAIM_DUPLICATE_THRESHOLD:
        report.skipped_duplicate_claims.append((text_norm, best_match.id, best_score))
        return None

    competency_ids = tuple(
        _resolve_competency(name, competencies, competency_index, used_ids, report)
        for name in extracted_claim.competency_names
    )

    new_id = _unique_id("claim", text_norm[:40], used_ids)
    claim = Claim(
        id=new_id,
        text=extracted_claim.text.strip(),
        importance=Importance.MEDIUM,
        visibility=Visibility.PUBLIC,
        confidence=ConfidenceLevel.CLAIMED,
        tags=tuple(extracted_claim.tags),
        position_id=position_id,
        competency_ids=competency_ids,
    )
    report.added_claims.append(new_id)

    if best_match is not None and best_score >= _CLAIM_POSSIBLE_DUPLICATE_THRESHOLD:
        report.possible_duplicate_claims.append((text_norm, best_match.id, best_score))

    return claim


def _build_evidence(claim_id: str, extracted_evidence: list[ExtractedEvidence], used_ids: set[str]) -> list[Evidence]:
    result = []
    for ev in extracted_evidence:
        metric = None
        if ev.metric_value is not None:
            direction = _coerce_enum(MetricDirection, ev.metric_direction, MetricDirection.ABSOLUTE)
            metric = Metric(value=ev.metric_value, unit=ev.metric_unit, direction=direction)
        new_id = _unique_id("evidence", ev.description[:40], used_ids)
        result.append(
            Evidence(
                id=new_id,
                type=EvidenceType.METRIC if metric else EvidenceType.OTHER,
                description=ev.description.strip(),
                metric=metric,
                confidence=ConfidenceLevel.CLAIMED,
                claim_id=claim_id,
            )
        )
    return result


def _resolve_credential(
    extracted: ExtractedCredential,
    org_id: str,
    credentials: list[Credential],
    credential_index: dict[tuple[str, str], str],
    used_ids: set[str],
    report: IngestReport,
) -> None:
    key = (extracted.title.strip().lower(), org_id)
    if key in credential_index:
        return
    credential_type = _coerce_enum(CredentialType, extracted.credential_type, CredentialType.OTHER)
    issue_date = _parse_flexible_date(extracted.issue_date) if extracted.issue_date else None
    new_id = _unique_id("cred", extracted.title, used_ids)
    credentials.append(
        Credential(
            id=new_id,
            title=extracted.title.strip(),
            credential_type=credential_type,
            issue_date=issue_date,
            organization_id=org_id,
        )
    )
    credential_index[key] = new_id
    report.added_credentials.append(new_id)


def resolve_extracted_resume(
    extracted: ExtractedResume,
    existing: ResumeDocument | None,
    embedding_provider: EmbeddingProvider | None = None,
) -> tuple[ResumeDocument, IngestReport]:
    report = IngestReport()

    if existing is None:
        person = Person(id="person_1", name=extracted.name, headline=extracted.headline, summary=extracted.summary)
        organizations: list[Organization] = []
        positions: list[Position] = []
        claims: list[Claim] = []
        competencies: list[Competency] = []
        artifacts: list[Artifact] = []
        evidence: list[Evidence] = []
        credentials: list[Credential] = []
    else:
        person = existing.person
        organizations = list(existing.organizations)
        positions = list(existing.positions)
        claims = list(existing.claims)
        competencies = list(existing.competencies)
        artifacts = list(existing.artifacts)
        evidence = list(existing.evidence)
        credentials = list(existing.credentials)

    used_ids = {
        person.id,
        *(o.id for o in organizations),
        *(p.id for p in positions),
        *(c.id for c in claims),
        *(c.id for c in competencies),
        *(a.id for a in artifacts),
        *(e.id for e in evidence),
        *(c.id for c in credentials),
    }

    org_index = {(o.name.strip().lower(), o.type.value): o.id for o in organizations}

    competency_index: dict[str, str] = {}
    for comp in competencies:
        competency_index.setdefault(comp.name.strip().lower(), comp.id)
        for alias in comp.aliases:
            competency_index.setdefault(alias.strip().lower(), comp.id)

    credential_index = {(c.title.strip().lower(), c.organization_id): c.id for c in credentials}

    claims_by_position: dict[str, list[Claim]] = {}
    independent_claims: list[Claim] = []
    for claim in claims:
        if claim.position_id is None:
            independent_claims.append(claim)
        else:
            claims_by_position.setdefault(claim.position_id, []).append(claim)

    for extracted_pos in extracted.positions:
        org_id = _resolve_organization(
            extracted_pos.organization_name, extracted_pos.organization_type, organizations, org_index, used_ids, report
        )
        position_id = _resolve_position(extracted_pos, org_id, positions, used_ids, embedding_provider, report)
        container = claims_by_position.setdefault(position_id, [])
        for extracted_claim in extracted_pos.claims:
            new_claim = _resolve_claim(
                extracted_claim, container, position_id, competencies, competency_index, used_ids,
                embedding_provider, report,
            )
            if new_claim is not None:
                claims.append(new_claim)
                container.append(new_claim)
                evidence.extend(_build_evidence(new_claim.id, extracted_claim.evidence, used_ids))

    for extracted_claim in extracted.independent_claims:
        new_claim = _resolve_claim(
            extracted_claim, independent_claims, None, competencies, competency_index, used_ids,
            embedding_provider, report,
        )
        if new_claim is not None:
            claims.append(new_claim)
            independent_claims.append(new_claim)
            evidence.extend(_build_evidence(new_claim.id, extracted_claim.evidence, used_ids))

    for extracted_cred in extracted.credentials:
        # Credentials of type "degree" are much more often issued by a
        # university than an employer; other types default to employer,
        # same as position organizations.
        default_org_type = "university" if extracted_cred.credential_type == "degree" else None
        org_id = _resolve_organization(
            extracted_cred.organization_name, default_org_type, organizations, org_index, used_ids, report
        )
        _resolve_credential(extracted_cred, org_id, credentials, credential_index, used_ids, report)

    document = ResumeDocument(
        person=person,
        organizations=tuple(organizations),
        positions=tuple(positions),
        claims=tuple(claims),
        competencies=tuple(competencies),
        artifacts=tuple(artifacts),
        evidence=tuple(evidence),
        credentials=tuple(credentials),
    )
    return document, report
