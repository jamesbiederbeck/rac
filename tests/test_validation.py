from rac.graph import ResumeGraph
from rac.model import (
    Claim,
    Competency,
    ConfidenceLevel,
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
from rac.validation import Severity, validate

PERSON = Person(id="p1", name="Test Person")


def _org(id_="org1", name="Acme", type_=OrganizationType.EMPLOYER):
    return Organization(id=id_, name=name, type=type_)


def test_valid_document_has_no_issues():
    doc = ResumeDocument(
        person=PERSON,
        organizations=[_org()],
        positions=[
            Position(
                id="pos1",
                title="Engineer",
                employment_type=EmploymentType.FULL_TIME,
                interval=DateOrInterval(start="2020-01-01", end="2021-01-01"),
                organization_id="org1",
            )
        ],
    )
    graph = ResumeGraph.build(doc)
    assert validate(graph) == []


def test_dangling_organization_reference_is_error():
    doc = ResumeDocument(
        person=PERSON,
        positions=[
            Position(
                id="pos1",
                title="Engineer",
                employment_type=EmploymentType.FULL_TIME,
                interval=DateOrInterval(start="2020-01-01"),
                organization_id="does_not_exist",
            )
        ],
    )
    graph = ResumeGraph.build(doc)
    issues = validate(graph)
    assert any(i.code == "dangling-reference" and i.severity == Severity.ERROR for i in issues)


def test_overlapping_full_time_positions_at_different_orgs_is_error():
    doc = ResumeDocument(
        person=PERSON,
        organizations=[_org("org1", "A"), _org("org2", "B")],
        positions=[
            Position(
                id="pos1",
                title="Eng",
                employment_type=EmploymentType.FULL_TIME,
                interval=DateOrInterval(start="2020-01-01", end="2021-06-01"),
                organization_id="org1",
            ),
            Position(
                id="pos2",
                title="Eng2",
                employment_type=EmploymentType.FULL_TIME,
                interval=DateOrInterval(start="2021-01-01", end="2022-01-01"),
                organization_id="org2",
            ),
        ],
    )
    graph = ResumeGraph.build(doc)
    issues = validate(graph)
    assert any(i.code == "overlapping-full-time-positions" for i in issues)


def test_overlapping_part_time_and_full_time_is_only_a_warning():
    doc = ResumeDocument(
        person=PERSON,
        organizations=[_org("org1", "A"), _org("org2", "B")],
        positions=[
            Position(
                id="pos1",
                title="Eng",
                employment_type=EmploymentType.FULL_TIME,
                interval=DateOrInterval(start="2020-01-01", end="2021-06-01"),
                organization_id="org1",
            ),
            Position(
                id="pos2",
                title="Consultant",
                employment_type=EmploymentType.CONTRACT,
                interval=DateOrInterval(start="2021-01-01", end="2022-01-01"),
                organization_id="org2",
            ),
        ],
    )
    graph = ResumeGraph.build(doc)
    issues = validate(graph)
    assert not any(i.severity == Severity.ERROR for i in issues)
    assert any(i.code == "overlapping-positions" and i.severity == Severity.WARNING for i in issues)


def test_position_with_no_claims_is_not_flagged():
    doc = ResumeDocument(
        person=PERSON,
        organizations=[_org()],
        positions=[
            Position(
                id="pos1",
                title="Cashier",
                employment_type=EmploymentType.PART_TIME,
                interval=DateOrInterval(start="2015-01-01", end="2016-01-01"),
                organization_id="org1",
            )
        ],
    )
    graph = ResumeGraph.build(doc)
    assert validate(graph) == []


def test_duplicate_competency_alias_is_error():
    doc = ResumeDocument(
        person=PERSON,
        competencies=[
            Competency(id="python", name="Python", aliases=["CPython"]),
            Competency(id="cpp", name="C++", aliases=["Python"]),
        ],
    )
    graph = ResumeGraph.build(doc)
    issues = validate(graph)
    assert any(i.code == "ambiguous-competency-alias" for i in issues)


def test_duplicate_entity_id_across_types_is_error():
    doc = ResumeDocument(
        person=PERSON,
        organizations=[_org(id_="dup1")],
        positions=[
            Position(
                id="dup1",
                title="Eng",
                employment_type=EmploymentType.FULL_TIME,
                interval=DateOrInterval(start="2020-01-01"),
                organization_id="dup1",
            )
        ],
    )
    graph = ResumeGraph.build(doc)
    issues = validate(graph)
    assert any(i.code == "duplicate-entity-id" for i in issues)


def test_person_with_no_positions_is_warning_only():
    doc = ResumeDocument(person=PERSON)
    graph = ResumeGraph.build(doc)
    issues = validate(graph)
    assert issues == [i for i in issues if i.severity == Severity.WARNING]
    assert any(i.code == "person-has-no-positions" for i in issues)


def test_claim_with_no_support_is_warning_only():
    doc = ResumeDocument(
        person=PERSON,
        claims=[
            Claim(
                id="c1",
                text="Did a thing",
                importance=Importance.LOW,
                visibility=Visibility.PUBLIC,
                confidence=ConfidenceLevel.CLAIMED,
            )
        ],
    )
    graph = ResumeGraph.build(doc)
    issues = validate(graph)
    assert issues == [
        i for i in issues if i.severity == Severity.WARNING
    ]
    assert any(i.code == "unsupported-unclassified-claim" for i in issues)
