import pytest

from rac.model import Claim, ConfidenceLevel, Importance, Visibility
from rac.ranking import cosine_similarity, rank_claims_by_query
from conftest import FakeEmbeddingProvider


def _claim(id_, text, importance=Importance.MEDIUM):
    return Claim(
        id=id_,
        text=text,
        importance=importance,
        visibility=Visibility.PUBLIC,
        confidence=ConfidenceLevel.CLAIMED,
    )


def test_cosine_similarity_identical_vectors_is_one():
    assert cosine_similarity((1.0, 2.0, 3.0), (1.0, 2.0, 3.0)) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors_is_zero():
    assert cosine_similarity((1.0, 0.0), (0.0, 1.0)) == pytest.approx(0.0)


def test_cosine_similarity_zero_vector_is_zero():
    assert cosine_similarity((0.0, 0.0), (1.0, 2.0)) == 0.0


def test_rank_claims_by_query_orders_by_similarity():
    provider = FakeEmbeddingProvider()
    claims = [
        _claim("c_bread", "baked bread for a bakery"),
        _claim("c_k8s", "led a kubernetes migration"),
    ]

    ranked = rank_claims_by_query(claims, "kubernetes rollout", provider)

    assert [c.id for c, _ in ranked] == ["c_k8s", "c_bread"]
    assert ranked[0][1] > ranked[1][1]


def test_rank_claims_by_query_dedups_identical_claim_text():
    provider = FakeEmbeddingProvider()
    claims = [
        _claim("c1", "led a kubernetes migration"),
        _claim("c2", "led a kubernetes migration"),
    ]

    rank_claims_by_query(claims, "kubernetes rollout", provider)

    # one call for the query, one for the (deduped) shared claim text
    assert provider.calls == ["kubernetes rollout", "led a kubernetes migration"]
