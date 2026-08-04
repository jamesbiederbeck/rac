from datetime import date

from rac.graph import ResumeGraph
from rac.model import (
    Claim,
    ConfidenceLevel,
    Credential,
    CredentialType,
    DateOrInterval,
    EmploymentType,
    Importance,
    Organization,
    OrganizationType,
    Person,
    Position,
    ResumeDocument,
    Visibility,
)
from rac.render.markdown import render_markdown
from rac.render.sections import build_resume_sections


def test_render_markdown_includes_header_experience_and_bullets():
    person = Person(id="p1", name="Jamie Rivera", headline="Senior SRE", summary="Reliability-focused engineer.")
    org = Organization(id="org1", name="Acme Cloud", type=OrganizationType.EMPLOYER)
    position = Position(
        id="pos1",
        title="Senior SRE",
        employment_type=EmploymentType.FULL_TIME,
        interval=DateOrInterval(start=date(2022, 3, 1)),
        organization_id="org1",
    )
    claim = Claim(
        id="c1",
        text="Reduced MTTR by 45%.",
        importance=Importance.HIGH,
        visibility=Visibility.PUBLIC,
        confidence=ConfidenceLevel.VERIFIED,
        position_id="pos1",
    )
    doc = ResumeDocument(person=person, organizations=[org], positions=[position], claims=[claim])
    graph = ResumeGraph.build(doc)
    sections = build_resume_sections(graph, [claim])

    md = render_markdown(sections)

    assert "# Jamie Rivera" in md
    assert "*Senior SRE*" in md
    assert "Reliability-focused engineer." in md
    assert "## Experience" in md
    assert "Senior SRE — Acme Cloud" in md
    assert "Mar 2022 – Present" in md
    assert "- Reduced MTTR by 45%." in md

    # Experience section appears before Skills in the output.
    assert md.index("## Experience") < md.index("Reduced MTTR")


def test_render_markdown_omits_parenthetical_when_credential_has_no_issue_date():
    person = Person(id="p1", name="Jamie Rivera")
    org = Organization(id="org1", name="State University", type=OrganizationType.UNIVERSITY)
    credential = Credential(
        id="cred1", title="B.S. Computer Science", credential_type=CredentialType.DEGREE, organization_id="org1"
    )
    doc = ResumeDocument(person=person, organizations=[org], credentials=[credential])
    graph = ResumeGraph.build(doc)
    sections = build_resume_sections(graph, [])

    md = render_markdown(sections)

    assert "- B.S. Computer Science — State University" in md
    assert "Unknown" not in md
