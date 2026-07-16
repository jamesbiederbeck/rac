from pathlib import Path

from rac.graph import ResumeGraph
from rac.model import (
    Claim,
    Competency,
    ConfidenceLevel,
    Importance,
    Person,
    ResumeDocument,
    Visibility,
)
from rac.profile import (
    BuildProfile,
    ProfileFilters,
    apply_profile,
    filter_claims,
    load_build_profile,
    score_by_weights,
)
from conftest import FakeEmbeddingProvider

PERSON = Person(id="p1", name="Test Person")
SAMPLE_PROFILE = Path(__file__).parent.parent / "examples" / "sample_profile.yaml"


def _claim(id_, text, importance=Importance.MEDIUM, tags=(), competency_ids=()):
    return Claim(
        id=id_,
        text=text,
        importance=importance,
        visibility=Visibility.PUBLIC,
        confidence=ConfidenceLevel.CLAIMED,
        tags=tags,
        competency_ids=competency_ids,
    )


def test_load_build_profile_from_yaml():
    profile = load_build_profile(SAMPLE_PROFILE)
    assert profile.name == "staff-sre"
    assert profile.query is not None


def test_filter_claims_include_tags():
    doc = ResumeDocument(
        person=PERSON,
        claims=[
            _claim("c1", "text one", tags=["reliability"]),
            _claim("c2", "text two", tags=["frontend"]),
        ],
    )
    graph = ResumeGraph.build(doc)
    profile = BuildProfile(name="p", filters=ProfileFilters(include_tags=["reliability"]))

    selected = filter_claims(graph, profile)

    assert [c.id for c in selected] == ["c1"]


def test_filter_claims_exclude_tags():
    doc = ResumeDocument(
        person=PERSON,
        claims=[
            _claim("c1", "text one", tags=["reliability"]),
            _claim("c2", "text two", tags=["frontend"]),
        ],
    )
    graph = ResumeGraph.build(doc)
    profile = BuildProfile(name="p", filters=ProfileFilters(exclude_tags=["frontend"]))

    selected = filter_claims(graph, profile)

    assert [c.id for c in selected] == ["c1"]


def test_score_by_weights_applies_matching_competency_weight():
    doc = ResumeDocument(
        person=PERSON,
        competencies=[Competency(id="comp_k8s", name="Kubernetes")],
        claims=[
            _claim("c1", "text one", importance=Importance.MEDIUM, competency_ids=["comp_k8s"]),
            _claim("c2", "text two", importance=Importance.MEDIUM),
        ],
    )
    graph = ResumeGraph.build(doc)
    profile = BuildProfile(name="p", weights={"kubernetes": 2.0})

    score_with_weight = score_by_weights(graph, doc.claims[0], profile)
    score_without_weight = score_by_weights(graph, doc.claims[1], profile)

    assert score_with_weight == score_without_weight * 2.0


def test_apply_profile_without_query_orders_by_weight_score():
    doc = ResumeDocument(
        person=PERSON,
        competencies=[Competency(id="comp_k8s", name="Kubernetes")],
        claims=[
            _claim("c_low", "low importance", importance=Importance.LOW),
            _claim("c_critical", "critical importance", importance=Importance.CRITICAL, competency_ids=["comp_k8s"]),
        ],
    )
    graph = ResumeGraph.build(doc)
    profile = BuildProfile(name="p", weights={"kubernetes": 2.0})

    ranked = apply_profile(graph, profile)

    assert [c.id for c, _ in ranked] == ["c_critical", "c_low"]


def test_apply_profile_with_query_uses_embedding_similarity():
    doc = ResumeDocument(
        person=PERSON,
        claims=[
            _claim("c_bread", "baked bread for a bakery"),
            _claim("c_k8s", "led a kubernetes migration"),
        ],
    )
    graph = ResumeGraph.build(doc)
    profile = BuildProfile(name="p", query="kubernetes rollout")
    provider = FakeEmbeddingProvider()

    ranked = apply_profile(graph, profile, provider=provider)

    assert [c.id for c, _ in ranked] == ["c_k8s", "c_bread"]
