"""
The shared contract between the two ways a resume PDF's text gets turned
into structured data (rac/ingest/llm.py's OpenAICompatibleExtractor, or a
Claude Code skill working agentically) and rac/ingest/resolve.py's merge
engine, which is the only thing that knows how to turn this into real RSM
entities.

Deliberately *not* the RSM itself: no ids, no cross-references, no dedup.
Just the flat facts a structuring step can plausibly pull out of resume
text. Assigning ids and resolving names against existing data (is "Acme
Cloud" the same Organization as one already in the document?) is
resolve.py's job, not this schema's.
"""

from __future__ import annotations

from pydantic import BaseModel


class ExtractedContact(BaseModel):
    method_type: str = "other"  # "email" | "phone" | "other"
    value: str
    label: str | None = None


class ExtractedLink(BaseModel):
    label: str
    url: str


class ExtractedEvidence(BaseModel):
    description: str
    metric_value: float | None = None
    metric_unit: str | None = None
    metric_direction: str | None = None  # "increase" | "decrease" | "absolute"


class ExtractedClaim(BaseModel):
    text: str
    tags: list[str] = []
    competency_names: list[str] = []
    evidence: list[ExtractedEvidence] = []


class ExtractedPosition(BaseModel):
    organization_name: str
    organization_type: str | None = None  # best guess at an OrganizationType value
    title: str
    employment_type: str | None = None  # best guess at an EmploymentType value
    start_date: str  # flexible: "2023-03-01", "2023-03", "March 2023", ...
    end_date: str | None = None  # None means ongoing/present
    claims: list[ExtractedClaim] = []


class ExtractedCredential(BaseModel):
    title: str
    credential_type: str | None = None  # best guess at a CredentialType value
    organization_name: str
    issue_date: str | None = None


class ExtractedResume(BaseModel):
    name: str
    headline: str | None = None
    summary: str | None = None
    contact_methods: list[ExtractedContact] = []
    links: list[ExtractedLink] = []
    positions: list[ExtractedPosition] = []
    independent_claims: list[ExtractedClaim] = []
    credentials: list[ExtractedCredential] = []
