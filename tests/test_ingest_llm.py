import json

import httpx
import pytest

from rac.ingest.extracted import ExtractedResume
from rac.ingest.llm import DEFAULT_BASE_URL, ExtractionError, OpenAICompatibleExtractor


def _chat_response(url, content: str):
    return httpx.Response(
        200,
        request=httpx.Request("POST", url),
        json={"choices": [{"message": {"content": content}}]},
    )


def test_extract_posts_schema_and_text_and_parses_result(monkeypatch):
    captured = {}
    valid_json = json.dumps({"name": "Jamie Rivera", "positions": []})

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _chat_response(url, valid_json)

    monkeypatch.setattr(httpx, "post", fake_post)

    extractor = OpenAICompatibleExtractor(api_key="test-key", model="test-model")
    result = extractor.extract("some resume text")

    assert isinstance(result, ExtractedResume)
    assert result.name == "Jamie Rivera"
    assert captured["url"] == f"{DEFAULT_BASE_URL}/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["json"]["model"] == "test-model"
    assert captured["json"]["response_format"] == {"type": "json_object"}
    assert captured["json"]["messages"][1] == {"role": "user", "content": "some resume text"}


def test_extract_raises_clear_error_on_malformed_json(monkeypatch):
    def fake_post(url, headers, json, timeout):
        return _chat_response(url, "not valid json at all")

    monkeypatch.setattr(httpx, "post", fake_post)

    extractor = OpenAICompatibleExtractor(api_key="test-key", model="test-model")
    with pytest.raises(ExtractionError):
        extractor.extract("some resume text")


def test_extract_raises_clear_error_when_schema_violated(monkeypatch):
    missing_name_field = json.dumps({"headline": "SRE"})  # missing required `name`

    def fake_post(url, headers, json, timeout):
        return _chat_response(url, missing_name_field)

    monkeypatch.setattr(httpx, "post", fake_post)

    extractor = OpenAICompatibleExtractor(api_key="test-key", model="test-model")
    with pytest.raises(ExtractionError):
        extractor.extract("some resume text")


def test_missing_api_key_raises_clear_error(monkeypatch):
    monkeypatch.delenv("RAC_LLM_API_KEY", raising=False)
    with pytest.raises(ExtractionError):
        OpenAICompatibleExtractor(model="test-model")


def test_missing_model_raises_clear_error(monkeypatch):
    monkeypatch.delenv("RAC_LLM_MODEL", raising=False)
    with pytest.raises(ExtractionError):
        OpenAICompatibleExtractor(api_key="test-key")


def test_base_url_from_env_var(monkeypatch):
    monkeypatch.setenv("RAC_LLM_BASE_URL", "http://localhost:9000/v1")
    extractor = OpenAICompatibleExtractor(api_key="test-key", model="test-model")
    assert extractor.base_url == "http://localhost:9000/v1"
