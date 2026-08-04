"""
LLM-driven producer of ExtractedResume data, for running `rac ingest`
standalone (outside Claude Code). Talks to any OpenAI-compatible chat
completions endpoint -- OpenRouter by default, or a self-hosted server.

This is the counterpart to the .claude/skills/ingest-resume/ skill, which
produces the same ExtractedResume shape agentically instead of via this
HTTP client. rac/ingest/resolve.py's merge engine doesn't care which
produced it.
"""

from __future__ import annotations

import json
import os
from typing import Protocol

import httpx
from pydantic import ValidationError

from rac.ingest.extracted import ExtractedResume

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

_SYSTEM_PROMPT_TEMPLATE = """\
You extract structured data from resume text. Read the resume text the user \
provides and return ONLY a single JSON object matching this JSON Schema, with \
no other commentary:

{schema}

Rules:
- Every position's dates go in start_date/end_date. Use "YYYY-MM-DD" if a day is \
given, "YYYY-MM" if only a month/year is known. Leave end_date null for a role \
that is still ongoing ("Present").
- employment_type must be one of: full_time, part_time, contract, internship, \
freelance, volunteer (guess full_time if genuinely unclear).
- organization_type must be one of: employer, university, nonprofit, government, \
conference, open_source_foundation, standards_body, other.
- credential_type must be one of: degree, certification, security_clearance, \
professional_license, other.
- Every bullet point under a role becomes one entry in that position's `claims`. \
Preserve the original wording -- do not rewrite, summarize, or embellish.
- Work history not tied to an employer (open source, personal projects) goes in \
`independent_claims`, not `positions`.
"""


class ExtractionError(RuntimeError):
    pass


class ExtractionProvider(Protocol):
    def extract(self, text: str) -> ExtractedResume:
        """Turn raw resume text into an ExtractedResume."""


class OpenAICompatibleExtractor:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("RAC_LLM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")

        api_key = api_key or os.environ.get("RAC_LLM_API_KEY")
        if not api_key:
            raise ExtractionError(
                "No LLM API key configured. Set RAC_LLM_API_KEY (and RAC_LLM_MODEL), or use "
                "`rac ingest --extracted <path>` with data produced by the ingest-resume skill instead."
            )
        self.api_key = api_key

        model = model or os.environ.get("RAC_LLM_MODEL")
        if not model:
            raise ExtractionError(
                "No LLM model configured. Set RAC_LLM_MODEL (e.g. an OpenRouter model id like "
                "'anthropic/claude-3.5-sonnet'), or use `rac ingest --extracted <path>` instead."
            )
        self.model = model

        self.timeout = timeout

    def extract(self, text: str) -> ExtractedResume:
        schema = json.dumps(ExtractedResume.model_json_schema())
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT_TEMPLATE.format(schema=schema)},
                    {"role": "user", "content": text},
                ],
            },
            timeout=self.timeout,
        )
        response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"]
        try:
            return ExtractedResume.model_validate_json(content)
        except (ValidationError, json.JSONDecodeError) as exc:
            raise ExtractionError(
                f"Model output did not match the expected schema: {exc}\n\nRaw output:\n{content}"
            ) from exc
