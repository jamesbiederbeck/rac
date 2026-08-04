import pytest

weasyprint = pytest.importorskip("weasyprint")

from rac.graph import ResumeGraph  # noqa: E402
from rac.model import Person, ResumeDocument  # noqa: E402
from rac.render.pdf import render_pdf  # noqa: E402
from rac.render.sections import build_resume_sections  # noqa: E402


def test_render_pdf_produces_valid_pdf_bytes():
    person = Person(id="p1", name="Jamie Rivera")
    doc = ResumeDocument(person=person)
    graph = ResumeGraph.build(doc)
    sections = build_resume_sections(graph, [])

    pdf_bytes = render_pdf(sections)

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF")
