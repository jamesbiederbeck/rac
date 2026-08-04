from datetime import date

from rac.graph import ResumeGraph
from rac.model import (
    Artifact,
    ArtifactType,
    Claim,
    Competency,
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
from rac.render.sections import build_resume_sections

PERSON = Person(id="p1", name="Test Person")


def _claim(id_, text, position_id=None, competency_ids=(), produced=(), referenced=()):
    return Claim(
        id=id_,
        text=text,
        importance=Importance.MEDIUM,
        visibility=Visibility.PUBLIC,
        confidence=ConfidenceLevel.CLAIMED,
        position_id=position_id,
        competency_ids=competency_ids,
        produced_artifact_ids=produced,
        referenced_artifact_ids=referenced,
    )


def test_experience_ordered_most_recent_first_and_open_ended_wins():
    org = Organization(id="org1", name="Acme", type=OrganizationType.EMPLOYER)
    old_position = Position(
        id="pos_old",
        title="Junior Dev",
        employment_type=EmploymentType.FULL_TIME,
        interval=DateOrInterval(start=date(2015, 1, 1), end=date(2018, 1, 1)),
        organization_id="org1",
    )
    current_position = Position(
        id="pos_current",
        title="Senior Dev",
        employment_type=EmploymentType.FULL_TIME,
        interval=DateOrInterval(start=date(2020, 1, 1)),  # open-ended
        organization_id="org1",
    )
    claims = [
        _claim("c_old", "old work", position_id="pos_old"),
        _claim("c_current", "current work", position_id="pos_current"),
    ]
    doc = ResumeDocument(
        person=PERSON,
        organizations=[org],
        positions=[old_position, current_position],
        claims=claims,
    )
    graph = ResumeGraph.build(doc)

    sections = build_resume_sections(graph, claims)

    assert [e.position.id for e in sections.experience] == ["pos_current", "pos_old"]
    assert sections.experience[0].organization.name == "Acme"


def test_position_with_no_included_claims_is_omitted():
    org = Organization(id="org1", name="Acme", type=OrganizationType.EMPLOYER)
    position = Position(
        id="pos1",
        title="Dev",
        employment_type=EmploymentType.FULL_TIME,
        interval=DateOrInterval(start=date(2020, 1, 1)),
        organization_id="org1",
    )
    doc = ResumeDocument(person=PERSON, organizations=[org], positions=[position], claims=[])
    graph = ResumeGraph.build(doc)

    sections = build_resume_sections(graph, [])

    assert sections.experience == ()


def test_independent_claims_bucketed_separately():
    claim = _claim("c1", "OSS work", position_id=None)
    doc = ResumeDocument(person=PERSON, claims=[claim])
    graph = ResumeGraph.build(doc)

    sections = build_resume_sections(graph, [claim])

    assert sections.independent_claims == (claim,)
    assert sections.experience == ()


def test_competencies_ordered_by_claim_count_then_name():
    comp_a = Competency(id="comp_a", name="Aardvark Wrangling")
    comp_b = Competency(id="comp_b", name="Kubernetes")
    claims = [
        _claim("c1", "text1", competency_ids=["comp_b"]),
        _claim("c2", "text2", competency_ids=["comp_b", "comp_a"]),
    ]
    doc = ResumeDocument(person=PERSON, competencies=[comp_a, comp_b], claims=claims)
    graph = ResumeGraph.build(doc)

    sections = build_resume_sections(graph, claims)

    assert [c.id for c in sections.competencies] == ["comp_b", "comp_a"]


def test_projects_resolve_produced_and_referenced_artifacts():
    artifact = Artifact(id="art1", name="kube-cost-cli", type=ArtifactType.OPEN_SOURCE_REPOSITORY)
    produced_claim = _claim("c1", "built it", produced=["art1"])
    referenced_claim = _claim("c2", "used it", referenced=["art1"])
    claims = [produced_claim, referenced_claim]
    doc = ResumeDocument(person=PERSON, artifacts=[artifact], claims=claims)
    graph = ResumeGraph.build(doc)

    sections = build_resume_sections(graph, claims)

    assert len(sections.projects) == 1
    entry = sections.projects[0]
    assert entry.artifact.id == "art1"
    assert entry.produced_by == (produced_claim,)
    assert entry.referenced_by == (referenced_claim,)


def test_credentials_ordered_most_recent_first():
    org = Organization(id="org1", name="State U", type=OrganizationType.UNIVERSITY)
    older = Credential(
        id="cred_old", title="B.S.", credential_type=CredentialType.DEGREE,
        issue_date=date(2010, 1, 1), organization_id="org1",
    )
    newer = Credential(
        id="cred_new", title="Cert", credential_type=CredentialType.CERTIFICATION,
        issue_date=date(2022, 1, 1), organization_id="org1",
    )
    doc = ResumeDocument(person=PERSON, organizations=[org], credentials=[older, newer])
    graph = ResumeGraph.build(doc)

    sections = build_resume_sections(graph, [])

    assert [e.credential.id for e in sections.credentials] == ["cred_new", "cred_old"]
