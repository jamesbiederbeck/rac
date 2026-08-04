import pytest

from rac.graph import ResumeGraph
from rac.model import Claim, ConfidenceLevel, Importance, Person, ResumeDocument, Visibility
from rac.render.paginate import PageLimitError, fit_claims_to_page_limit, order_by_importance

PERSON = Person(id="p1", name="Test Person")


def _claim(id_, text, importance):
    return Claim(
        id=id_,
        text=text,
        importance=importance,
        visibility=Visibility.PUBLIC,
        confidence=ConfidenceLevel.CLAIMED,
    )


def test_order_by_importance_sorts_critical_first_stable_on_ties():
    claims = [
        _claim("c1", "low one", Importance.LOW),
        _claim("c2", "critical one", Importance.CRITICAL),
        _claim("c3", "medium one", Importance.MEDIUM),
        _claim("c4", "critical two", Importance.CRITICAL),
    ]

    ordered = order_by_importance(claims)

    assert [c.id for c in ordered] == ["c2", "c4", "c3", "c1"]


def test_fit_claims_to_page_limit_drops_lowest_priority_first():
    pytest.importorskip("weasyprint")

    # Long claim texts to reliably force multiple pages under a tight limit.
    claims = [
        _claim(f"c{i}", "A very long claim sentence. " * 40, Importance.CRITICAL if i == 0 else Importance.LOW)
        for i in range(8)
    ]
    doc = ResumeDocument(person=PERSON, claims=claims)
    graph = ResumeGraph.build(doc)

    survivors, page_count = fit_claims_to_page_limit(graph, claims, page_limit=1)

    assert page_count <= 1
    assert len(survivors) < len(claims)
    # Trimming drops from the tail, so the highest-priority claim (first in
    # the ranked order passed in) is always kept until nothing else is left.
    assert survivors[0].id == "c0"


def test_fit_claims_to_page_limit_raises_when_nothing_left_to_drop():
    pytest.importorskip("weasyprint")

    doc = ResumeDocument(person=PERSON, claims=[])
    graph = ResumeGraph.build(doc)

    with pytest.raises(PageLimitError):
        fit_claims_to_page_limit(graph, [], page_limit=0)
