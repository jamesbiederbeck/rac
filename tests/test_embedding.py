import httpx
import pytest

from rac.embedding import EmbeddingClient, EmbeddingNotConfiguredError


def test_embed_posts_text_and_returns_vector(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return httpx.Response(
            200, request=httpx.Request("POST", url), json={"text": json["text"], "vector": [0.1, 0.2, 0.3]}
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    client = EmbeddingClient(base_url="http://example.test:8081")
    vector = client.embed("some claim text")

    assert vector == (0.1, 0.2, 0.3)
    assert captured["url"] == "http://example.test:8081/vectors"
    assert captured["json"] == {"text": "some claim text"}


def test_raises_when_unconfigured(monkeypatch):
    monkeypatch.delenv("RAC_EMBEDDING_URL", raising=False)
    with pytest.raises(EmbeddingNotConfiguredError):
        EmbeddingClient()


def test_base_url_from_env_var(monkeypatch):
    monkeypatch.setenv("RAC_EMBEDDING_URL", "http://other-host:9000")
    client = EmbeddingClient()
    assert client.base_url == "http://other-host:9000"


def test_embed_raises_on_http_error(monkeypatch):
    def fake_post(url, json, timeout):
        return httpx.Response(500, request=httpx.Request("POST", url), json={"error": "boom"})

    monkeypatch.setattr(httpx, "post", fake_post)

    client = EmbeddingClient(base_url="http://example.test:8081")
    with pytest.raises(httpx.HTTPStatusError):
        client.embed("text")
