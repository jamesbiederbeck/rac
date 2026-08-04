"""
Render a ResumeSections projection to a single self-contained HTML document
(inline <style>, no external assets) so rac.render.pdf can convert the same
output with WeasyPrint. All user-supplied text is passed through
html.escape -- Claim/Person text is free-form and not trusted to be safe
markup.
"""

from __future__ import annotations

from datetime import date
from html import escape

from rac.render.sections import ResumeSections

_STYLE = """
body { font-family: Georgia, 'Times New Roman', serif; max-width: 42em; margin: 2em auto;
       color: #1a1a1a; line-height: 1.45; }
h1 { margin-bottom: 0.1em; }
.headline { color: #444; font-style: italic; margin-top: 0; }
.contact { color: #555; font-size: 0.9em; }
.contact a { color: #555; }
h2 { border-bottom: 1px solid #ccc; padding-bottom: 0.2em; margin-top: 1.5em; }
.entry-header { margin-bottom: 0; }
.entry-meta { color: #666; font-size: 0.9em; margin-top: 0; }
ul { margin-top: 0.3em; }
.skills { color: #333; }
"""


def _format_date(d: date) -> str:
    return d.strftime("%b %Y")


def _format_interval(start: date, end: date | None) -> str:
    return f"{_format_date(start)} – {_format_date(end) if end else 'Present'}"


def _format_employment_type(employment_type: str) -> str:
    return employment_type.replace("_", " ").title()


def render_html(sections: ResumeSections) -> str:
    person = sections.person
    parts: list[str] = [
        "<!doctype html>",
        "<html><head>",
        f"<title>{escape(person.name)}</title>",
        '<meta charset="utf-8">',
        f"<style>{_STYLE}</style>",
        "</head><body>",
        f"<h1>{escape(person.name)}</h1>",
    ]

    if person.headline:
        parts.append(f'<p class="headline">{escape(person.headline)}</p>')

    contact_bits = [escape(method.value) for method in person.contact_methods]
    contact_bits += [f'<a href="{escape(link.url)}">{escape(link.label)}</a>' for link in person.links]
    if contact_bits:
        parts.append(f'<p class="contact">{" | ".join(contact_bits)}</p>')

    if person.summary:
        parts.append(f"<p>{escape(person.summary)}</p>")

    if sections.experience:
        parts.append("<h2>Experience</h2>")
        for entry in sections.experience:
            org_name = entry.organization.name if entry.organization else "Unknown Organization"
            interval = _format_interval(entry.position.interval.start, entry.position.interval.end)
            employment = _format_employment_type(entry.position.employment_type.value)
            parts.append(
                f'<p class="entry-header"><strong>{escape(entry.position.title)}</strong> '
                f"— {escape(org_name)}</p>"
            )
            parts.append(f'<p class="entry-meta">{escape(interval)} · {escape(employment)}</p>')
            parts.append("<ul>")
            parts += [f"<li>{escape(claim.text)}</li>" for claim in entry.claims]
            parts.append("</ul>")

    if sections.independent_claims:
        parts.append("<h2>Additional Contributions</h2><ul>")
        parts += [f"<li>{escape(claim.text)}</li>" for claim in sections.independent_claims]
        parts.append("</ul>")

    if sections.competencies:
        parts.append("<h2>Skills</h2>")
        parts.append(f'<p class="skills">{", ".join(escape(c.name) for c in sections.competencies)}</p>')

    if sections.projects:
        parts.append("<h2>Projects</h2>")
        for entry in sections.projects:
            if entry.artifact.url:
                title = f'<a href="{escape(entry.artifact.url)}">{escape(entry.artifact.name)}</a>'
            else:
                title = escape(entry.artifact.name)
            parts.append(f'<p class="entry-header"><strong>{title}</strong></p>')
            if entry.artifact.description:
                parts.append(f"<p>{escape(entry.artifact.description)}</p>")

    if sections.credentials:
        parts.append("<h2>Education &amp; Credentials</h2><ul>")
        for entry in sections.credentials:
            org_name = entry.organization.name if entry.organization else "Unknown Organization"
            if entry.credential.issue_date:
                issued = f" ({escape(_format_date(entry.credential.issue_date))})"
            else:
                issued = ""
            parts.append(f"<li>{escape(entry.credential.title)} — {escape(org_name)}{issued}</li>")
        parts.append("</ul>")

    parts.append("</body></html>")
    return "\n".join(parts)
