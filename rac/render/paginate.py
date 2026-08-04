"""
Fits a resume's Claims to a PDF page limit by iteratively dropping the
lowest-priority Claim and re-rendering until WeasyPrint's page count is
within the limit, or nothing is left to drop.

Only meaningful for PDF -- Markdown/HTML have no discrete "page" concept,
so page-limit fitting only applies to `--format pdf` (see rac/cli.py).
Requires the optional `pdf` extra for the same reason rac/render/pdf.py
does; `weasyprint` is imported lazily here too.
"""

from __future__ import annotations

from typing import Sequence

from rac.graph import ResumeGraph
from rac.model import Claim, Importance
from rac.render.html import render_html
from rac.render.sections import build_resume_sections

_IMPORTANCE_RANK = {
    Importance.CRITICAL: 0,
    Importance.HIGH: 1,
    Importance.MEDIUM: 2,
    Importance.LOW: 3,
}


class PageLimitError(RuntimeError):
    pass


def order_by_importance(claims: Sequence[Claim]) -> list[Claim]:
    """Fallback priority order (highest priority first) for deciding what
    to trim when no profile-driven rank score is available: Claim.importance
    descending, stable on ties (Python's sort is stable)."""
    return sorted(claims, key=lambda c: _IMPORTANCE_RANK[c.importance])


def _pdf_page_count(html: str) -> int:
    import weasyprint

    return len(weasyprint.HTML(string=html).render().pages)


def fit_claims_to_page_limit(
    graph: ResumeGraph, ranked_claims: Sequence[Claim], page_limit: int
) -> tuple[list[Claim], int]:
    """Drop the lowest-priority (last) Claim one at a time until the
    rendered PDF fits within `page_limit` pages. `ranked_claims` must
    already be ordered highest-priority first; the survivors are returned
    in that same relative order (callers that want to preserve original
    document order should re-filter their own claim list by the returned
    ids rather than use this order directly for rendering).

    Raises PageLimitError if even zero Claims doesn't fit -- the Person
    header/Skills/Credentials alone exceed the limit.
    """
    claims = list(ranked_claims)
    while True:
        sections = build_resume_sections(graph, claims)
        page_count = _pdf_page_count(render_html(sections))
        if page_count <= page_limit:
            return claims, page_count
        if not claims:
            raise PageLimitError(
                f"Cannot fit within {page_limit} page(s) even with zero Claims "
                f"(header/skills/credentials alone take {page_count})."
            )
        claims = claims[:-1]
