---
name: ingest-resume
description: Ingest a resume PDF into this repo's RSM YAML (resume.yaml), merging with any existing content instead of duplicating positions/claims. Use when the user asks to ingest, import, or add a resume PDF to their RSM data, or points at a resume PDF file anywhere on disk.
---

# Ingest a resume PDF

`rac ingest` needs structured resume data as JSON (matching `rac/ingest/extracted.py`'s
`ExtractedResume` schema) before it can merge anything. Outside Claude Code, `rac ingest`
gets that by calling an OpenAI-compatible LLM API (`RAC_LLM_API_KEY`/`RAC_LLM_MODEL`). Inside
Claude Code, do the structuring yourself and hand `rac ingest` the result via `--extracted` —
no API key needed.

## Steps

1. **Extract text.** Run `pdftotext -layout <pdf> -` (poppler-utils, no Python dependency) against
   whatever resume PDF the user pointed at. If the output is empty or only a few dozen characters,
   the PDF is scanned/image-only — stop and tell the user OCR isn't supported yet, don't guess
   from nothing.

2. **Structure it.** Read the extracted text and produce a single JSON object matching
   `rac/ingest/extracted.py`'s `ExtractedResume` model:
   - `name`, `headline`, `summary`, `contact_methods` (`method_type`: `email`/`phone`/`other`),
     `links`.
   - `positions`: one entry per employer, each with `organization_name`, `organization_type`
     (`employer`/`university`/`nonprofit`/`government`/`conference`/`open_source_foundation`/
     `standards_body`/`other`), `title`, `employment_type` (`full_time`/`part_time`/`contract`/
     `internship`/`freelance`/`volunteer` — guess `full_time` if unclear), `start_date`/
     `end_date` as `"YYYY-MM-DD"` or `"YYYY-MM"` (`end_date: null` for a role still ongoing),
     and `claims` (one per bullet point — **preserve the original wording**, don't rewrite or
     summarize).
   - `independent_claims`: bullets not tied to any employer (open source, personal projects).
   - `credentials`: `title`, `credential_type` (`degree`/`certification`/`security_clearance`/
     `professional_license`/`other`), `organization_name`, `issue_date`.
   - Run `python3 -c "import json; from rac.ingest.extracted import ExtractedResume; print(json.dumps(ExtractedResume.model_json_schema(), indent=2))"`
     if you want the exact schema rather than relying on this summary.

3. **Write it to a temp file** (e.g. under the session scratchpad), then preview the merge:
   ```bash
   rac ingest <pdf> --into resume.yaml --extracted <tmpfile>.json
   ```
   This is a dry run by default — nothing is written yet. Read the printed report: what got
   added vs. reused as an existing Position/Organization/Competency, any skipped exact
   duplicates, and any "possible duplicate" or date-mismatch notes.

4. **Show the user the report** and ask before applying. Only re-run with `--apply` after they
   confirm — this writes real, possibly-PII personal data (phone, email, employment history) to
   `resume.yaml`, and merge decisions (especially "possible duplicate" claims and Position
   date-mismatch notes) are heuristic, not certain.

5. After `--apply`, run `rac validate resume.yaml` to confirm the merged document is still
   clean.

## Notes

- Never fabricate content. Every Claim's `text` should be the resume's actual wording, not a
  paraphrase — evidenced by rsm_spec.md's Claim/Evidence design (facts over formatting).
- Resume PDFs and any extracted JSON contain real personal data (contact info, employment
  history). Don't write them into a tracked path in this repo — use a scratch/temp location, and
  never commit a real `resume.yaml` (see `.gitignore`).
