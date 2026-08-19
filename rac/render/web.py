"""
Render a ResumeSections projection to a single self-contained "web" HTML
document: a fixed sidebar nav plus full-height scrolling sections, styled
after github.com/StartBootstrap/startbootstrap-resume but with the Bootstrap/jQuery/
Font Awesome/Google Fonts CDN dependencies replaced by inline CSS/JS and
system fonts, so the output has no external network calls (unlike the
source site, which pulls those from CDNs and reports to Google Analytics).

This is a second HTML output alongside rac.render.html.render_html -- that
one is the plain single-column document PDF rendering shares; this one is
a browser-first landing-page-style resume with in-page navigation. Both
consume the same format-independent ResumeSections IR and share nothing
else, so neither can regress the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from html import escape

from rac.render.sections import ResumeSections

_PRIMARY = "#bd5d38"

_STYLE = f"""
:root {{ --primary: {_PRIMARY}; }}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  color: #212529;
  line-height: 1.6;
}}
a {{ color: var(--primary); }}
#side-nav {{
  background: var(--primary);
  color: #fff;
  padding: 1.5rem 1rem;
}}
#side-nav .name {{
  font-weight: 800;
  font-size: 1.1rem;
  text-align: center;
  margin-bottom: 1rem;
}}
#side-nav ul {{
  list-style: none;
  margin: 0;
  padding: 0;
}}
#side-nav a {{
  display: block;
  color: #fff;
  text-decoration: none;
  font-weight: 800;
  letter-spacing: 0.05rem;
  text-transform: uppercase;
  font-size: 0.85rem;
  padding: 0.5rem 0;
}}
#side-nav a:hover {{ opacity: 0.8; }}
main {{ padding: 0 1.5rem; max-width: 60rem; }}
section {{ padding: 3rem 0; border-bottom: 1px solid #eee; }}
section:last-child {{ border-bottom: none; }}
h1 {{ margin-bottom: 0.1em; }}
h2 {{
  text-transform: uppercase;
  letter-spacing: 0.05rem;
  border-bottom: 2px solid var(--primary);
  display: inline-block;
  padding-bottom: 0.2em;
}}
.headline {{ color: #555; font-style: italic; margin-top: 0; font-size: 1.2rem; }}
.contact {{ color: #555; }}
.contact a {{ color: var(--primary); }}
.entry {{ margin-bottom: 2rem; display: flex; flex-wrap: wrap; justify-content: space-between; gap: 0.5rem; }}
.entry-main {{ flex: 1 1 30rem; }}
.entry-header {{ margin-bottom: 0; }}
.entry-org {{ color: #555; font-weight: 600; margin: 0.1em 0 0.5em; }}
.entry-meta {{ color: var(--primary); font-weight: 600; white-space: nowrap; }}
.skills-list {{ display: flex; flex-wrap: wrap; gap: 0.5rem; padding: 0; list-style: none; }}
.skills-list li {{
  background: #f1f1f1;
  border-radius: 1rem;
  padding: 0.3rem 0.9rem;
  font-size: 0.9rem;
}}
@media (min-width: 62rem) {{
  body {{ display: flex; }}
  #side-nav {{
    position: fixed;
    top: 0;
    left: 0;
    width: 16rem;
    height: 100vh;
    overflow-y: auto;
    text-align: center;
  }}
  main {{ margin-left: 16rem; padding: 0 3rem; }}
}}
"""

_SCRIPT = """
document.querySelectorAll('#side-nav a').forEach(function (link) {
  link.addEventListener('click', function (event) {
    var target = document.querySelector(link.getAttribute('href'));
    if (!target) return;
    event.preventDefault();
    target.scrollIntoView({ behavior: 'smooth' });
  });
});
"""


@dataclass(frozen=True)
class _NavItem:
    anchor: str
    label: str


def _format_date(d: date) -> str:
    return d.strftime("%b %Y")


def _format_interval(start: date, end: date | None) -> str:
    return f"{_format_date(start)} – {_format_date(end) if end else 'Present'}"


def _format_employment_type(employment_type: str) -> str:
    return employment_type.replace("_", " ").title()


def render_web(sections: ResumeSections) -> str:
    person = sections.person
    nav_items: list[_NavItem] = [_NavItem("about", "About")]
    summary_html = f"<p>{escape(person.summary)}</p>" if person.summary else ""

    body: list[str] = []

    if sections.experience:
        nav_items.append(_NavItem("experience", "Experience"))
        body.append('<section id="experience"><h2>Experience</h2>')
        for entry in sections.experience:
            org_name = entry.organization.name if entry.organization else "Unknown Organization"
            interval = _format_interval(entry.position.interval.start, entry.position.interval.end)
            employment = _format_employment_type(entry.position.employment_type.value)
            body.append(
                '<div class="entry"><div class="entry-main">'
                f'<h3 class="entry-header">{escape(entry.position.title)}</h3>'
                f'<p class="entry-org">{escape(org_name)}</p>'
                "<ul>" + "".join(f"<li>{escape(claim.text)}</li>" for claim in entry.claims) + "</ul>"
                "</div>"
                f'<div class="entry-meta">{escape(interval)}<br>{escape(employment)}</div>'
                "</div>"
            )
        body.append("</section>")

    if sections.independent_claims:
        nav_items.append(_NavItem("contributions", "Contributions"))
        body.append(
            '<section id="contributions"><h2>Additional Contributions</h2><ul>'
            + "".join(f"<li>{escape(claim.text)}</li>" for claim in sections.independent_claims)
            + "</ul></section>"
        )

    if sections.competencies:
        nav_items.append(_NavItem("skills", "Skills"))
        body.append(
            '<section id="skills"><h2>Skills</h2><ul class="skills-list">'
            + "".join(f"<li>{escape(c.name)}</li>" for c in sections.competencies)
            + "</ul></section>"
        )

    if sections.projects:
        nav_items.append(_NavItem("projects", "Projects"))
        body.append('<section id="projects"><h2>Projects</h2>')
        for entry in sections.projects:
            if entry.artifact.url:
                title = f'<a href="{escape(entry.artifact.url)}">{escape(entry.artifact.name)}</a>'
            else:
                title = escape(entry.artifact.name)
            body.append(f'<div class="entry"><div class="entry-main"><h3 class="entry-header">{title}</h3>')
            if entry.artifact.description:
                body.append(f"<p>{escape(entry.artifact.description)}</p>")
            body.append("</div></div>")
        body.append("</section>")

    if sections.credentials:
        nav_items.append(_NavItem("education", "Education"))
        body.append('<section id="education"><h2>Education &amp; Credentials</h2><ul>')
        for entry in sections.credentials:
            org_name = entry.organization.name if entry.organization else "Unknown Organization"
            issued = f" ({escape(_format_date(entry.credential.issue_date))})" if entry.credential.issue_date else ""
            body.append(f"<li>{escape(entry.credential.title)} — {escape(org_name)}{issued}</li>")
        body.append("</ul></section>")

    nav_html = "".join(f'<li><a href="#{item.anchor}">{escape(item.label)}</a></li>' for item in nav_items)

    contact_bits = [escape(method.value) for method in person.contact_methods]
    contact_bits += [f'<a href="{escape(link.url)}">{escape(link.label)}</a>' for link in person.links]
    contact_html = f'<p class="contact">{" · ".join(contact_bits)}</p>' if contact_bits else ""
    headline_html = f'<p class="headline">{escape(person.headline)}</p>' if person.headline else ""

    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en"><head>',
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{escape(person.name)}</title>",
            f"<style>{_STYLE}</style>",
            "</head><body>",
            '<nav id="side-nav">',
            f'<div class="name">{escape(person.name)}</div>',
            f"<ul>{nav_html}</ul>",
            "</nav>",
            "<main>",
            '<section id="about">',
            f"<h1>{escape(person.name)}</h1>",
            headline_html,
            contact_html,
            summary_html,
            "</section>",
            *body,
            "</main>",
            f"<script>{_SCRIPT}</script>",
            "</body></html>",
        ]
    )
