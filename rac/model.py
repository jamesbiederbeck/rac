"""
The Resume Semantic Model (RSM), as data.

This module is a direct code mapping of `rsm_spec.md`. It defines the closed
set of enumerations, value objects, and entities that make up the RSM. It
has no knowledge of storage format or presentation — see `rac.storage` for
serialization and `rac.graph` for the assembled, cross-referenced graph.

All models are frozen (immutable): a build operates on one snapshot; a new
snapshot is a new set of objects, never a mutation in place.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# ---------------------------------------------------------------------------
# Enumerations (RSM §12)
# ---------------------------------------------------------------------------


class EmploymentType(str, Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    FREELANCE = "freelance"
    VOLUNTEER = "volunteer"


class OrganizationType(str, Enum):
    EMPLOYER = "employer"
    UNIVERSITY = "university"
    NONPROFIT = "nonprofit"
    GOVERNMENT = "government"
    CONFERENCE = "conference"
    OPEN_SOURCE_FOUNDATION = "open_source_foundation"
    STANDARDS_BODY = "standards_body"
    OTHER = "other"


class ArtifactType(str, Enum):
    INTERNAL_SERVICE = "internal_service"
    OPEN_SOURCE_REPOSITORY = "open_source_repository"
    PATENT = "patent"
    RESEARCH_PAPER = "research_paper"
    PRESENTATION = "presentation"
    LIBRARY = "library"
    WEBSITE = "website"
    PRODUCT = "product"
    OTHER = "other"


class EvidenceType(str, Enum):
    METRIC = "metric"
    AWARD = "award"
    REPOSITORY_LINK = "repository_link"
    INCIDENT_REPORT = "incident_report"
    CUSTOMER_IMPACT = "customer_impact"
    PUBLICATION = "publication"
    PERFORMANCE_REVIEW = "performance_review"
    TESTIMONIAL = "testimonial"
    OTHER = "other"


class CredentialType(str, Enum):
    DEGREE = "degree"
    CERTIFICATION = "certification"
    SECURITY_CLEARANCE = "security_clearance"
    PROFESSIONAL_LICENSE = "professional_license"
    OTHER = "other"


class CompetencyCategory(str, Enum):
    TECHNICAL = "technical"
    LEADERSHIP = "leadership"
    DOMAIN_KNOWLEDGE = "domain_knowledge"
    PROCESS = "process"
    COMMUNICATION = "communication"
    OTHER = "other"


class Visibility(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    DRAFT = "draft"


class ConfidenceLevel(str, Enum):
    CLAIMED = "claimed"
    CORROBORATED = "corroborated"
    VERIFIED = "verified"


class Importance(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MetricDirection(str, Enum):
    INCREASE = "increase"
    DECREASE = "decrease"
    ABSOLUTE = "absolute"


class ContactMethodType(str, Enum):
    EMAIL = "email"
    PHONE = "phone"
    OTHER = "other"


# ---------------------------------------------------------------------------
# Value objects (RSM §5) — immutable, no identity, compared structurally.
# ---------------------------------------------------------------------------


class ContactMethod(_Frozen):
    method_type: ContactMethodType
    value: str
    label: str | None = None

    @model_validator(mode="after")
    def _label_required_for_other(self) -> "ContactMethod":
        if self.method_type == ContactMethodType.OTHER and not self.label:
            raise ValueError("ContactMethod.label is required when method_type is 'other'")
        return self


class Link(_Frozen):
    label: str
    url: str


class Location(_Frozen):
    city: str | None = None
    region: str | None = None
    country: str | None = None
    remote: bool = False


class DateOrInterval(_Frozen):
    start: date
    end: date | None = None

    @model_validator(mode="after")
    def _end_not_before_start(self) -> "DateOrInterval":
        if self.end is not None and self.end < self.start:
            raise ValueError("DateOrInterval.end must not precede .start")
        return self

    @property
    def is_open_ended(self) -> bool:
        return self.end is None


class Metric(_Frozen):
    value: float
    unit: str | None = None
    direction: MetricDirection


# ---------------------------------------------------------------------------
# Entities (RSM §4) — identity-bearing, referenced/owned by `id`.
# ---------------------------------------------------------------------------


class Person(_Frozen):
    id: str
    name: str
    headline: str | None = None
    summary: str | None = None
    contact_methods: tuple[ContactMethod, ...] = ()
    links: tuple[Link, ...] = ()
    location: Location | None = None

    @model_validator(mode="after")
    def _name_non_empty(self) -> "Person":
        if not self.name.strip():
            raise ValueError("Person.name must be non-empty")
        return self


class Organization(_Frozen):
    id: str
    name: str
    type: OrganizationType
    website: str | None = None
    location: Location | None = None

    @model_validator(mode="after")
    def _name_non_empty(self) -> "Organization":
        if not self.name.strip():
            raise ValueError("Organization.name must be non-empty")
        return self


class Position(_Frozen):
    id: str
    title: str
    employment_type: EmploymentType
    interval: DateOrInterval
    location: Location | None = None
    organization_id: str


class Claim(_Frozen):
    id: str
    text: str
    importance: Importance
    visibility: Visibility
    confidence: ConfidenceLevel
    tags: tuple[str, ...] = ()

    # Ownership: exactly one of `position_id` (owned by a Position) or
    # unset (owned directly by Person, i.e. an independent claim). See
    # RSM §4.4 and §6 ("container exclusivity").
    position_id: str | None = None

    competency_ids: tuple[str, ...] = ()
    produced_artifact_ids: tuple[str, ...] = ()
    referenced_artifact_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _text_non_empty(self) -> "Claim":
        if not self.text.strip():
            raise ValueError("Claim.text must be non-empty")
        return self

    @model_validator(mode="after")
    def _produced_referenced_disjoint(self) -> "Claim":
        overlap = set(self.produced_artifact_ids) & set(self.referenced_artifact_ids)
        if overlap:
            raise ValueError(
                f"Claim {self.id!r}: artifact(s) {sorted(overlap)} cannot be both "
                "PRODUCED and REFERENCES for the same claim"
            )
        return self


class Competency(_Frozen):
    id: str
    name: str
    category: CompetencyCategory | None = None
    aliases: tuple[str, ...] = ()


class Artifact(_Frozen):
    id: str
    name: str
    type: ArtifactType
    description: str | None = None
    url: str | None = None


class Evidence(_Frozen):
    id: str
    type: EvidenceType
    description: str
    metric: Metric | None = None
    source: str | None = None
    confidence: ConfidenceLevel

    # Owning claim (RSM §4.7: Evidence is owned by exactly one Claim).
    claim_id: str

    @model_validator(mode="after")
    def _description_non_empty(self) -> "Evidence":
        if not self.description.strip():
            raise ValueError("Evidence.description must be non-empty")
        return self


class Credential(_Frozen):
    id: str
    title: str
    credential_type: CredentialType
    issue_date: date | None = None
    expiration_date: date | None = None
    organization_id: str  # ISSUED_BY
    competency_ids: tuple[str, ...] = ()  # VALIDATES

    @model_validator(mode="after")
    def _expiration_not_before_issue(self) -> "Credential":
        if self.issue_date and self.expiration_date and self.expiration_date < self.issue_date:
            raise ValueError("Credential.expiration_date must not precede .issue_date")
        return self


# ---------------------------------------------------------------------------
# Top-level document: the full set of entities for one Person's RSM instance.
# ---------------------------------------------------------------------------


class ResumeDocument(_Frozen):
    """The complete, storage-independent set of RSM entities for one Person.

    This is what a storage adapter reads and writes. It is *not* the graph —
    see `rac.graph.ResumeGraph` for the cross-referenced, index-backed view
    used by validation, ranking, and rendering.
    """

    person: Person
    organizations: tuple[Organization, ...] = ()
    positions: tuple[Position, ...] = ()
    claims: tuple[Claim, ...] = ()
    competencies: tuple[Competency, ...] = ()
    artifacts: tuple[Artifact, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    credentials: tuple[Credential, ...] = ()
