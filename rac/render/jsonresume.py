"""
Project a ResumeSections IR into a JSON Resume (jsonresume.org) document.

This is a second export target alongside markdown.py/html.py/web.py: instead
of rendering directly, it produces the flat schema JSON Resume themes are
written against (see https://jsonresume.org/theme-development), so any
theme package following that contract -- not just rac's own built-in HTML/
web templates -- can render the same underlying data. rac.render.theme is
the part that actually invokes a theme package with this output.

JSON Resume is a flat CV schema with no concept of Evidence, Claim
confidence/importance/tags, or Competency category -- those are already
gone by the time a ResumeSections reaches here, the same way they're absent
from markdown.py/html.py's output. The one loss specific to this export
(rac's own templates don't have it) is independent Claims: Person-direct
claims with no owning Position or Artifact have no home in JSON Resume's
schema (no section for a claim that isn't part of some `work`/`projects`
entry), so `sections.independent_claims` is not represented here at all.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from rac.model import ContactMethodType, CredentialType
from rac.render.sections import ResumeSections


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d is not None else None


def _compact(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None and v != []}


def _basics(sections: ResumeSections) -> dict[str, Any]:
    person = sections.person
    email = next((m.value for m in person.contact_methods if m.method_type == ContactMethodType.EMAIL), None)
    phone = next((m.value for m in person.contact_methods if m.method_type == ContactMethodType.PHONE), None)

    location = None
    if person.location:
        location = _compact(
            {
                "city": person.location.city,
                "region": person.location.region,
                "countryCode": person.location.country,
            }
        )

    return _compact(
        {
            "name": person.name,
            "label": person.headline,
            "email": email,
            "phone": phone,
            "summary": person.summary,
            "location": location or None,
            "url": person.links[0].url if person.links else None,
            "profiles": [{"network": link.label, "url": link.url} for link in person.links],
        }
    )


def _work(sections: ResumeSections) -> list[dict[str, Any]]:
    entries = []
    for entry in sections.experience:
        entries.append(
            _compact(
                {
                    "position": entry.position.title,
                    "name": entry.organization.name if entry.organization else "Unknown Organization",
                    "url": entry.organization.website if entry.organization else None,
                    "startDate": _iso(entry.position.interval.start),
                    "endDate": _iso(entry.position.interval.end),
                    "highlights": [claim.text for claim in entry.claims],
                }
            )
        )
    return entries


def _education_and_certificates(sections: ResumeSections) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    education: list[dict[str, Any]] = []
    certificates: list[dict[str, Any]] = []
    for entry in sections.credentials:
        org_name = entry.organization.name if entry.organization else "Unknown Organization"
        if entry.credential.credential_type == CredentialType.DEGREE:
            education.append(
                _compact(
                    {
                        "institution": org_name,
                        "studyType": entry.credential.title,
                        "startDate": _iso(entry.credential.issue_date),
                        "endDate": _iso(entry.credential.expiration_date),
                    }
                )
            )
        else:
            certificates.append(
                _compact(
                    {
                        "name": entry.credential.title,
                        "date": _iso(entry.credential.issue_date),
                        "issuer": org_name,
                    }
                )
            )
    return education, certificates


def _skills(sections: ResumeSections) -> list[dict[str, Any]]:
    return [_compact({"name": c.name, "keywords": list(c.aliases)}) for c in sections.competencies]


def _projects(sections: ResumeSections) -> list[dict[str, Any]]:
    entries = []
    for entry in sections.projects:
        entries.append(
            _compact(
                {
                    "name": entry.artifact.name,
                    "description": entry.artifact.description,
                    "url": entry.artifact.url,
                    "highlights": [c.text for c in (*entry.produced_by, *entry.referenced_by)],
                }
            )
        )
    return entries


def to_json_resume(sections: ResumeSections) -> dict[str, Any]:
    """Project `sections` into a JSON Resume (jsonresume.org) document."""
    education, certificates = _education_and_certificates(sections)
    return _compact(
        {
            "basics": _basics(sections),
            "work": _work(sections),
            "education": education,
            "certificates": certificates,
            "skills": _skills(sections),
            "projects": _projects(sections),
        }
    )
