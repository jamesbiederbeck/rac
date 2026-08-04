from rac.graph import ResumeGraph
from rac.model import (
    Claim,
    ConfidenceLevel,
    Credential,
    CredentialType,
    Importance,
    Organization,
    OrganizationType,
    Person,
    ResumeDocument,
    Visibility,
)
from rac.render.sections import build_resume_sections
from rac.render.web import render_web


def test_render_web_escapes_user_text():
    person = Person(id="p1", name="Jamie <script>alert(1)</script> Rivera")
    claim = Claim(
        id="c1",
        text="Grew revenue by 10% & shipped fast",
        importance=Importance.MEDIUM,
        visibility=Visibility.PUBLIC,
        confidence=ConfidenceLevel.CLAIMED,
        position_id=None,
    )
    doc = ResumeDocument(person=person, claims=[claim])
    graph = ResumeGraph.build(doc)
    sections = build_resume_sections(graph, [claim])

    html = render_web(sections)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "Grew revenue by 10% &amp; shipped fast" in html
    assert "<h1>Jamie" in html
    assert "Additional Contributions" in html


def test_render_web_is_a_well_formed_document_with_no_external_assets():
    person = Person(id="p1", name="Jamie Rivera")
    doc = ResumeDocument(person=person)
    graph = ResumeGraph.build(doc)
    sections = build_resume_sections(graph, [])

    html = render_web(sections)

    assert html.startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")
    assert "http://" not in html
    assert "https://" not in html


def test_render_web_nav_only_lists_present_sections():
    person = Person(id="p1", name="Jamie Rivera")
    org = Organization(id="org1", name="State University", type=OrganizationType.UNIVERSITY)
    credential = Credential(
        id="cred1", title="B.S. Computer Science", credential_type=CredentialType.DEGREE, organization_id="org1"
    )
    doc = ResumeDocument(person=person, organizations=[org], credentials=[credential])
    graph = ResumeGraph.build(doc)
    sections = build_resume_sections(graph, [])

    html = render_web(sections)

    assert '<a href="#education">Education</a>' in html
    assert '<a href="#experience">Experience</a>' not in html
    assert '<a href="#skills">Skills</a>' not in html
    assert "B.S. Computer Science — State University" in html
