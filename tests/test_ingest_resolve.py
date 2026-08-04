from datetime import date

from rac.ingest.extracted import ExtractedClaim, ExtractedCredential, ExtractedPosition, ExtractedResume
from rac.ingest.resolve import resolve_extracted_resume
from rac.model import (
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

PERSON = Person(id="person_1", name="Jamie Rivera")


class ScriptedEmbeddingProvider:
    """Exact string -> vector lookup, same style as tests/conftest.py's
    FakeEmbeddingProvider, but with vectors chosen for precise cosine
    similarity values so dedup-threshold behavior is fully deterministic."""

    def __init__(self, vectors: dict[str, tuple[float, float]]):
        self.vectors = vectors
        self.calls: list[str] = []

    def embed(self, text: str):
        self.calls.append(text)
        return self.vectors[text]


def _claim(id_, text, position_id=None, competency_ids=()):
    return Claim(
        id=id_,
        text=text,
        importance=Importance.MEDIUM,
        visibility=Visibility.PUBLIC,
        confidence=ConfidenceLevel.CLAIMED,
        position_id=position_id,
        competency_ids=competency_ids,
    )


def test_fresh_document_created_when_no_existing():
    extracted = ExtractedResume(
        name="Jamie Rivera",
        headline="SRE",
        positions=[
            ExtractedPosition(
                organization_name="Acme Cloud",
                organization_type="employer",
                title="Senior SRE",
                start_date="2022-03-01",
                claims=[ExtractedClaim(text="Reduced MTTR by 45%.")],
            )
        ],
    )

    document, report = resolve_extracted_resume(extracted, existing=None)

    assert document.person.id == "person_1"
    assert document.person.name == "Jamie Rivera"
    assert len(document.organizations) == 1
    assert len(document.positions) == 1
    assert len(document.claims) == 1
    assert report.added_organizations == [document.organizations[0].id]
    assert report.added_positions == [document.positions[0].id]
    assert report.added_claims == [document.claims[0].id]


def test_organization_reused_on_exact_name_and_type_match():
    org = Organization(id="org_acme", name="Acme Cloud", type=OrganizationType.EMPLOYER)
    existing = ResumeDocument(person=PERSON, organizations=[org])
    extracted = ExtractedResume(
        name="Jamie Rivera",
        positions=[
            ExtractedPosition(
                organization_name="Acme Cloud",
                organization_type="employer",
                title="Senior SRE",
                start_date="2022-03-01",
            )
        ],
    )

    document, report = resolve_extracted_resume(extracted, existing)

    assert len(document.organizations) == 1
    assert document.positions[0].organization_id == "org_acme"
    assert report.added_organizations == []


def test_organization_reused_by_name_when_guessed_type_differs():
    org = Organization(id="org_acme", name="Acme Cloud", type=OrganizationType.EMPLOYER)
    existing = ResumeDocument(person=PERSON, organizations=[org])
    extracted = ExtractedResume(
        name="Jamie Rivera",
        positions=[
            ExtractedPosition(
                organization_name="Acme Cloud",
                organization_type="other",  # LLM guessed wrong -- should still match by name
                title="Senior SRE",
                start_date="2022-03-01",
            )
        ],
    )

    document, _ = resolve_extracted_resume(extracted, existing)

    assert len(document.organizations) == 1
    assert document.positions[0].organization_id == "org_acme"


def test_position_reused_when_org_interval_and_title_match():
    org = Organization(id="org_acme", name="Acme Cloud", type=OrganizationType.EMPLOYER)
    position = Position(
        id="pos_acme_sre",
        title="Senior SRE",
        employment_type=EmploymentType.FULL_TIME,
        interval=DateOrInterval(start=date(2022, 3, 1)),
        organization_id="org_acme",
    )
    existing_claim = _claim("claim_old", "Existing bullet.", position_id="pos_acme_sre")
    existing = ResumeDocument(
        person=PERSON, organizations=[org], positions=[position], claims=[existing_claim]
    )
    extracted = ExtractedResume(
        name="Jamie Rivera",
        positions=[
            ExtractedPosition(
                organization_name="Acme Cloud",
                title="Senior SRE",
                start_date="2022-03-01",
                claims=[ExtractedClaim(text="A brand new bullet.")],
            )
        ],
    )

    document, report = resolve_extracted_resume(extracted, existing)

    assert len(document.positions) == 1
    assert report.added_positions == []
    new_claim_texts = {c.text for c in document.claims if c.position_id == "pos_acme_sre"}
    assert new_claim_texts == {"Existing bullet.", "A brand new bullet."}


def test_position_match_with_differing_dates_is_left_unchanged_and_noted():
    org = Organization(id="org_acme", name="Acme Cloud", type=OrganizationType.EMPLOYER)
    position = Position(
        id="pos_acme_sre",
        title="Senior SRE",
        employment_type=EmploymentType.FULL_TIME,
        interval=DateOrInterval(start=date(2022, 3, 1), end=date(2023, 1, 1)),
        organization_id="org_acme",
    )
    existing = ResumeDocument(person=PERSON, organizations=[org], positions=[position])
    extracted = ExtractedResume(
        name="Jamie Rivera",
        positions=[
            ExtractedPosition(
                organization_name="Acme Cloud", title="Senior SRE", start_date="2022-03-01"  # now open-ended
            )
        ],
    )

    document, report = resolve_extracted_resume(extracted, existing)

    assert document.positions[0].interval.end == date(2023, 1, 1)  # unchanged
    assert any("dates differ" in note for note in report.notes)


def test_rehire_at_same_org_and_title_creates_second_position():
    org = Organization(id="org_acme", name="Acme Cloud", type=OrganizationType.EMPLOYER)
    old_stint = Position(
        id="pos_acme_sre",
        title="SRE",
        employment_type=EmploymentType.FULL_TIME,
        interval=DateOrInterval(start=date(2015, 1, 1), end=date(2016, 1, 1)),
        organization_id="org_acme",
    )
    existing = ResumeDocument(person=PERSON, organizations=[org], positions=[old_stint])
    extracted = ExtractedResume(
        name="Jamie Rivera",
        positions=[
            ExtractedPosition(
                organization_name="Acme Cloud", title="SRE", start_date="2022-03-01"  # years later, not adjacent
            )
        ],
    )

    document, report = resolve_extracted_resume(extracted, existing)

    assert len(document.positions) == 2
    assert len(report.added_positions) == 1
    assert document.positions[0].id != document.positions[1].id


def test_claim_exact_text_duplicate_is_skipped():
    existing_claim = _claim("claim_existing", "Reduced MTTR by 45%.")
    existing = ResumeDocument(person=PERSON, claims=[existing_claim])
    extracted = ExtractedResume(
        name="Jamie Rivera", independent_claims=[ExtractedClaim(text="  Reduced   MTTR by 45%.  ")]
    )

    document, report = resolve_extracted_resume(extracted, existing)

    assert len(document.claims) == 1
    assert report.skipped_duplicate_claims == [("Reduced MTTR by 45%.", "claim_existing", 1.0)]


def test_claim_high_similarity_reworded_duplicate_is_skipped():
    existing_claim = _claim("claim_existing", "existing text")
    existing = ResumeDocument(person=PERSON, claims=[existing_claim])
    extracted = ExtractedResume(name="Jamie Rivera", independent_claims=[ExtractedClaim(text="reworded duplicate")])
    provider = ScriptedEmbeddingProvider(
        {"existing text": (1.0, 0.0), "reworded duplicate": (0.95, 0.3122)}  # cosine ~0.95
    )

    document, report = resolve_extracted_resume(extracted, existing, embedding_provider=provider)

    assert len(document.claims) == 1
    assert len(report.skipped_duplicate_claims) == 1
    assert report.skipped_duplicate_claims[0][1] == "claim_existing"


def test_claim_moderate_similarity_is_added_but_flagged_possible_duplicate():
    existing_claim = _claim("claim_existing", "existing text")
    existing = ResumeDocument(person=PERSON, claims=[existing_claim])
    extracted = ExtractedResume(name="Jamie Rivera", independent_claims=[ExtractedClaim(text="somewhat related")])
    provider = ScriptedEmbeddingProvider(
        {"existing text": (1.0, 0.0), "somewhat related": (0.8, 0.6)}  # cosine = 0.8
    )

    document, report = resolve_extracted_resume(extracted, existing, embedding_provider=provider)

    assert len(document.claims) == 2
    assert len(report.possible_duplicate_claims) == 1
    assert report.possible_duplicate_claims[0][1] == "claim_existing"
    assert report.skipped_duplicate_claims == []


def test_claim_low_similarity_is_added_cleanly():
    existing_claim = _claim("claim_existing", "existing text")
    existing = ResumeDocument(person=PERSON, claims=[existing_claim])
    extracted = ExtractedResume(name="Jamie Rivera", independent_claims=[ExtractedClaim(text="unrelated content")])
    provider = ScriptedEmbeddingProvider(
        {"existing text": (1.0, 0.0), "unrelated content": (0.0, 1.0)}  # cosine = 0.0
    )

    document, report = resolve_extracted_resume(extracted, existing, embedding_provider=provider)

    assert len(document.claims) == 2
    assert report.possible_duplicate_claims == []
    assert report.skipped_duplicate_claims == []


def test_claim_dedup_falls_back_to_exact_match_without_provider():
    existing_claim = _claim("claim_existing", "existing text")
    existing = ResumeDocument(person=PERSON, claims=[existing_claim])
    extracted = ExtractedResume(name="Jamie Rivera", independent_claims=[ExtractedClaim(text="different text")])

    document, report = resolve_extracted_resume(extracted, existing, embedding_provider=None)

    assert len(document.claims) == 2
    assert report.skipped_duplicate_claims == []
    assert report.possible_duplicate_claims == []


def test_competency_reused_by_name_or_alias():
    comp = Competency(id="comp_k8s", name="Kubernetes", aliases=["k8s"])
    existing = ResumeDocument(person=PERSON, competencies=[comp])
    extracted = ExtractedResume(
        name="Jamie Rivera", independent_claims=[ExtractedClaim(text="Did k8s stuff.", competency_names=["k8s"])]
    )

    document, report = resolve_extracted_resume(extracted, existing)

    assert len(document.competencies) == 1
    assert document.claims[0].competency_ids == ("comp_k8s",)
    assert report.added_competencies == []


def test_credential_reused_by_title_and_organization():
    org = Organization(id="org_wgu", name="Western Governors University", type=OrganizationType.UNIVERSITY)
    cred = Credential(
        id="cred_bs", title="B.S. IT", credential_type=CredentialType.DEGREE, organization_id="org_wgu"
    )
    existing = ResumeDocument(person=PERSON, organizations=[org], credentials=[cred])
    extracted = ExtractedResume(
        name="Jamie Rivera",
        credentials=[
            ExtractedCredential(title="B.S. IT", credential_type="degree", organization_name="Western Governors University")
        ],
    )

    document, report = resolve_extracted_resume(extracted, existing)

    assert len(document.credentials) == 1
    assert report.added_credentials == []
