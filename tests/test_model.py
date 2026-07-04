import pytest
from pydantic import ValidationError

from rac.model import (
    Claim,
    ConfidenceLevel,
    Credential,
    CredentialType,
    DateOrInterval,
    Evidence,
    EvidenceType,
    Importance,
    Visibility,
)


def test_claim_requires_non_empty_text():
    with pytest.raises(ValidationError):
        Claim(
            id="c1",
            text="   ",
            importance=Importance.LOW,
            visibility=Visibility.PUBLIC,
            confidence=ConfidenceLevel.CLAIMED,
        )


def test_claim_rejects_same_artifact_as_produced_and_referenced():
    with pytest.raises(ValidationError):
        Claim(
            id="c1",
            text="Built and used the same thing",
            importance=Importance.LOW,
            visibility=Visibility.PUBLIC,
            confidence=ConfidenceLevel.CLAIMED,
            produced_artifact_ids=["art1"],
            referenced_artifact_ids=["art1"],
        )


def test_date_or_interval_rejects_end_before_start():
    with pytest.raises(ValidationError):
        DateOrInterval(start="2022-01-01", end="2021-01-01")


def test_date_or_interval_open_ended():
    interval = DateOrInterval(start="2022-01-01")
    assert interval.is_open_ended


def test_credential_rejects_expiration_before_issue():
    with pytest.raises(ValidationError):
        Credential(
            id="cred1",
            title="Cert",
            credential_type=CredentialType.CERTIFICATION,
            issue_date="2022-01-01",
            expiration_date="2021-01-01",
            organization_id="org1",
        )


def test_evidence_requires_non_empty_description():
    with pytest.raises(ValidationError):
        Evidence(
            id="ev1",
            type=EvidenceType.METRIC,
            description="  ",
            confidence=ConfidenceLevel.CLAIMED,
            claim_id="c1",
        )


def test_entities_are_frozen():
    claim = Claim(
        id="c1",
        text="Did a thing",
        importance=Importance.LOW,
        visibility=Visibility.PUBLIC,
        confidence=ConfidenceLevel.CLAIMED,
    )
    with pytest.raises(ValidationError):
        claim.text = "Did another thing"
