"""Render a ResumeSections projection to Markdown. No new dependency."""

from __future__ import annotations

from datetime import date

from rac.render.sections import ResumeSections


def _format_date(d: date) -> str:
    return d.strftime("%b %Y")


def _format_interval(start: date, end: date | None) -> str:
    return f"{_format_date(start)} – {_format_date(end) if end else 'Present'}"


def _format_employment_type(employment_type: str) -> str:
    return employment_type.replace("_", " ").title()


def render_markdown(sections: ResumeSections) -> str:
    person = sections.person
    lines: list[str] = [f"# {person.name}"]

    if person.headline:
        lines.append(f"*{person.headline}*")

    contact_bits = []
    for method in person.contact_methods:
        contact_bits.append(method.value)
    for link in person.links:
        contact_bits.append(f"[{link.label}]({link.url})")
    if contact_bits:
        lines.append(" | ".join(contact_bits))

    if person.summary:
        lines += ["", person.summary]

    if sections.experience:
        lines += ["", "## Experience"]
        for entry in sections.experience:
            org_name = entry.organization.name if entry.organization else "Unknown Organization"
            interval = _format_interval(entry.position.interval.start, entry.position.interval.end)
            employment = _format_employment_type(entry.position.employment_type.value)
            lines.append(f"\n### {entry.position.title} — {org_name}")
            lines.append(f"*{interval} · {employment}*")
            for claim in entry.claims:
                lines.append(f"- {claim.text}")

    if sections.independent_claims:
        lines += ["", "## Additional Contributions"]
        for claim in sections.independent_claims:
            lines.append(f"- {claim.text}")

    if sections.competencies:
        lines += ["", "## Skills"]
        lines.append(", ".join(c.name for c in sections.competencies))

    if sections.projects:
        lines += ["", "## Projects"]
        for entry in sections.projects:
            title = f"[{entry.artifact.name}]({entry.artifact.url})" if entry.artifact.url else entry.artifact.name
            lines.append(f"\n### {title}")
            if entry.artifact.description:
                lines.append(entry.artifact.description)

    if sections.credentials:
        lines += ["", "## Education & Credentials"]
        for entry in sections.credentials:
            org_name = entry.organization.name if entry.organization else "Unknown Organization"
            if entry.credential.issue_date:
                lines.append(f"- {entry.credential.title} — {org_name} ({_format_date(entry.credential.issue_date)})")
            else:
                lines.append(f"- {entry.credential.title} — {org_name}")

    return "\n".join(lines) + "\n"
