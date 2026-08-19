from datetime import date

from rac.model import (
    Claim,
    ConfidenceLevel,
    ContactMethod,
    ContactMethodType,
    Credential,
    CredentialType,
    DateOrInterval,
    EmploymentType,
    Importance,
    Link,
    Organization,
    OrganizationType,
    Person,
    Position,
    Visibility,
)
from rac.render.jsonresume import to_json_resume
from rac.render.sections import CredentialEntry, ExperienceEntry, ResumeSections


def test_to_json_resume_maps_basics_and_work():
    person = Person(
        id="p1",
        name="Jamie Rivera",
        headline="Staff Engineer",
        summary="Builds things.",
        contact_methods=(ContactMethod(method_type=ContactMethodType.EMAIL, value="jamie@example.com"),),
        links=(Link(label="GitHub", url="https://github.com/jamie"),),
    )
    org = Organization(id="org1", name="Acme Corp", type=OrganizationType.EMPLOYER)
    position = Position(
        id="pos1",
        title="Staff Engineer",
        employment_type=EmploymentType.FULL_TIME,
        interval=DateOrInterval(start=date(2020, 1, 1)),
        organization_id="org1",
    )
    claim = Claim(
        id="c1",
        text="Shipped the thing",
        importance=Importance.HIGH,
        visibility=Visibility.PUBLIC,
        confidence=ConfidenceLevel.VERIFIED,
        position_id="pos1",
    )
    sections = ResumeSections(
        person=person,
        experience=(ExperienceEntry(position=position, organization=org, claims=(claim,)),),
    )

    resume = to_json_resume(sections)

    assert resume["basics"]["name"] == "Jamie Rivera"
    assert resume["basics"]["label"] == "Staff Engineer"
    assert resume["basics"]["email"] == "jamie@example.com"
    assert resume["basics"]["profiles"] == [{"network": "GitHub", "url": "https://github.com/jamie"}]
    assert resume["work"] == [
        {
            "position": "Staff Engineer",
            "name": "Acme Corp",
            "startDate": "2020-01-01",
            "highlights": ["Shipped the thing"],
        }
    ]


def test_to_json_resume_splits_degrees_from_certificates():
    person = Person(id="p1", name="Jamie Rivera")
    org = Organization(id="org1", name="State University", type=OrganizationType.UNIVERSITY)
    aws = Organization(id="org2", name="Amazon", type=OrganizationType.OTHER)
    degree = Credential(
        id="cred1", title="B.S. Computer Science", credential_type=CredentialType.DEGREE, organization_id="org1"
    )
    cert = Credential(
        id="cred2",
        title="Solutions Architect",
        credential_type=CredentialType.CERTIFICATION,
        organization_id="org2",
        issue_date=date(2022, 6, 1),
    )
    sections = ResumeSections(
        person=person,
        credentials=(
            CredentialEntry(credential=degree, organization=org),
            CredentialEntry(credential=cert, organization=aws),
        ),
    )

    resume = to_json_resume(sections)

    assert resume["education"] == [{"institution": "State University", "studyType": "B.S. Computer Science"}]
    assert resume["certificates"] == [{"name": "Solutions Architect", "date": "2022-06-01", "issuer": "Amazon"}]


def test_to_json_resume_omits_independent_claims():
    person = Person(id="p1", name="Jamie Rivera")
    claim = Claim(
        id="c1",
        text="Wrote a popular open-source library",
        importance=Importance.HIGH,
        visibility=Visibility.PUBLIC,
        confidence=ConfidenceLevel.CLAIMED,
        position_id=None,
    )
    sections = ResumeSections(person=person, independent_claims=(claim,))

    resume = to_json_resume(sections)

    assert "Wrote a popular open-source library" not in str(resume)
    assert resume == {"basics": {"name": "Jamie Rivera"}}
