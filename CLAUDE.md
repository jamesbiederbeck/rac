# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Resume-as-Code (RaC): a declarative resume generation system built on the Resume Semantic Model (RSM). The RSM is a storage-independent, presentation-independent semantic graph of a candidate's professional claims — the sole source of truth consumed by validation, AI transforms, ranking, and rendering. Two normative specs govern the design and must be treated as authoritative when writing or reviewing code:

- `rsm_spec.md` — the RSM itself: entities, value objects, relationships, ownership/cardinality rules, validation rules, normalization rules, lifecycle rules. This is the spec each module's docstring points back to (e.g. `rac/model.py` is "a direct code mapping of rsm_spec.md").
- `project_plan.md` — the overall system architecture (storage → parser → graph → plugins → build pipeline → renderer) and long-term scope (build profiles, themes, plugins, search). Only a small slice of this (the RSM core + YAML storage + validation) is implemented so far; most of `project_plan.md` describes future work, not current code.

When a modeling question comes up (can this field be optional, is this relationship owning or referencing, is this a hard error or a warning), check `rsm_spec.md` first — it is normative and the code is expected to conform to it, not the other way around.

## Commands

```bash
source .venv/bin/activate       # project uses a local venv
pip install -e ".[dev]"         # install package + pytest

pytest                          # run all tests
pytest tests/test_model.py      # run one file
pytest tests/test_model.py::test_claim_requires_non_empty_text  # run one test
pytest -k overlap               # run tests matching a keyword

rac init resume.yaml --name "Jane Doe"   # create a starter YAML resume
rac validate resume.yaml                 # validate a resume file against the RSM
rac rank resume.yaml profile.yaml        # filter + rank Claims per a build profile
rac render resume.yaml --format markdown|html|pdf [--profile profile.yaml] [--output path]
rac ingest resume.pdf --into resume.yaml [--extracted extracted.json] [--apply]
```

`rac rank`/`rac render --profile` talk to a text-embedding HTTP service when a profile has a `query`, configured via `RAC_EMBEDDING_URL` (no default — there's no bundled service). If it's unset or unreachable, both commands fall back to weight-based ranking with a warning rather than failing; profiles without `query` don't need it at all.

`rac render --format pdf` requires the optional `pdf` extra (`pip install -e ".[pdf]"`, pulls in WeasyPrint) — markdown/html rendering and every other command work with the base install.

`rac ingest` needs structured resume data before it can merge anything; without `--extracted`, it calls an OpenAI-compatible LLM API (`RAC_LLM_API_KEY`/`RAC_LLM_MODEL`, defaults to OpenRouter). Inside Claude Code, prefer the `.claude/skills/ingest-resume/` skill instead — it does the structuring agentically and hands the result to `rac ingest --extracted`, no API key needed. Either way, `rac ingest` defaults to a dry-run preview; `--apply` is required to actually write.

There is no configured linter/formatter/type-checker in `pyproject.toml` — don't assume `ruff`/`mypy`/`black` are wired up unless you check first.

## Architecture

Three layers, each with a distinct responsibility and file:

- **`rac/model.py`** — the RSM as pydantic data. All entities and value objects are frozen/immutable (`ConfigDict(frozen=True, extra="forbid")`): a build consumes one snapshot; edits produce a new set of objects, never in-place mutation. `ResumeDocument` is the flat, storage-independent bag of all entities for one Person (what storage adapters read/write). Per-entity/local invariants (non-empty text, date ordering, produced/referenced disjointness on a single Claim) are enforced here via pydantic `model_validator`s, because pydantic raises `ValidationError` at construction time.
- **`rac/graph.py`** — `ResumeGraph.build(document)` turns the flat `ResumeDocument` into an index-backed view: id→entity lookups and reverse indices (claims by position, evidence by claim, etc.), plus the derived properties from RSM §10 (`claim_count_for_competency`, `reference_count_for_artifact`, `effective_confidence`). It performs no validation — it assumes the document may be invalid and builds indices anyway, deliberately, so the validator can inspect a graph built from bad data.
- **`rac/validation.py`** — everything that requires seeing the *whole graph* rather than one entity: referential integrity (dangling `ref(Entity)` ids), global uniqueness, cardinality (at most one open-ended Position), the position-overlap rules, competency/organization normalization, orphan detection. Returns a flat `list[Issue]` tagged `Severity.ERROR` or `Severity.WARNING` — never raises. The error/warning split for each rule is spec-defined in `rsm_spec.md`, not a judgment call to make locally (e.g. overlapping positions is a warning unless both are full-time at different orgs, which is an error).
- **`rac/storage/`** — `StorageAdapter` (`base.py`) is the abstract load/save interface; `YamlStorageAdapter` is the only implementation so far, storing the full `ResumeDocument` as one YAML file with relationships expressed as id references. Additional backends (SQLite, remote API — see `project_plan.md`) should implement the same interface without changing what a `ResumeDocument` means.
- **`rac/profile.py`** — `BuildProfile` (the filtering/weighting config from `project_plan.md`'s "Build Profiles" section: `filters.include_tags`/`exclude_tags`, `weights` keyed by Competency name, plus a `query` field for embedding-based ranking). `filter_claims` applies tag filters; `score_by_weights` is the non-embedding fallback score (Claim.importance × average matching competency weight); `apply_profile` ties both together, using embedding similarity as the primary score when `query` + an `EmbeddingProvider` are supplied. `theme`/`page_limit` are accepted (spec fields) but unused — no renderer exists yet.
- **`rac/ranking.py`** — `rank_claims_by_query` scores Claims by cosine similarity between their text and a free-text prompt, via an `EmbeddingProvider` (deduping identical Claim text before embedding). Pure-Python cosine similarity, no numpy — vectors from the embedding service are not assumed pre-normalized.
- **`rac/embedding.py`** — `EmbeddingProvider` is the `Protocol` consumed by `ranking.py`; `EmbeddingClient` is the concrete HTTP implementation, talking to a `/vectors`-style embeddings-proxy. No default `base_url` — raises `EmbeddingNotConfiguredError` at construction if neither `base_url` nor `RAC_EMBEDDING_URL` is set; callers that treat embedding ranking as optional (`rac/cli.py`'s `_apply_profile_with_fallback`, `rac ingest`) catch that alongside `httpx.HTTPError` and degrade to `provider=None` instead of failing. Tests use a fake provider (`tests/conftest.py`) instead of hitting the network.
- **`rac/render/`** — projects a `ResumeGraph` + a caller-selected set of Claims into an output document; no Theme system exists yet (`BuildProfile.theme` stays accepted-but-unused, same as `page_limit`), so this ships one built-in look rather than pluggable themes. `sections.py` builds a format-independent IR (`ResumeSections`: Experience grouped by Position, ordered most-recent-first with open-ended positions sorting as current; independent Person-direct claims; Competencies deduped and ordered by `graph.claim_count_for_competency`; Projects resolved from PRODUCED/REFERENCES artifact ids; Credentials ordered by issue date) — this is the only place section derivation logic lives, per rsm_spec.md §14 ("rendering is a projection of the model"). `markdown.py` and `html.py` each consume that IR independently (`html.py` runs all user text through `html.escape`); `pdf.py` renders the same HTML through WeasyPrint (imported lazily — see the `pdf` extra note above) so HTML and PDF share one template. Claim *selection* (profile filtering, plus an always-on public-visibility-only policy) is deliberately left to the caller (`rac/cli.py`), not baked into this package.
- **`rac/ingest/`** — turns a resume PDF into RSM data and merges it into an existing `ResumeDocument` without duplicating Positions/Claims that already exist under different wording. `extract.py` shells out to `pdftotext -layout` (poppler-utils) for text; `extracted.py` defines `ExtractedResume`, the flat id-less schema a structuring step must produce (no ids, no dedup — that's `resolve.py`'s job); `llm.py`'s `OpenAICompatibleExtractor` is one way to produce that schema (any OpenAI-compatible chat endpoint, OpenRouter by default) — the `.claude/skills/ingest-resume/` skill is the other, producing the same schema agentically instead of via HTTP. `resolve.py`'s `resolve_extracted_resume` is the actual merge engine: Organizations dedup by `(name, type)` per `rsm_spec.md` §9.3 (actually *applying* the rule `validation.py`'s `_check_organization_dedup` only flags); Positions dedup by same-org + overlapping-or-adjacent interval + similar title (exact or, with an `EmbeddingProvider`, cosine-similarity-based — reuses `rac/ranking.py`'s `cosine_similarity` for a second purpose beyond query ranking); Claims dedup within a matched Position first by exact text, then by embedding similarity above a threshold (skip) or a lower threshold (add but flag as a possible duplicate); Competencies dedup via the RSM's own §9.1 name/alias rule. Nothing is decided silently — every add/skip/ambiguous match is recorded in the returned `IngestReport`, which `rac ingest` prints; the CLI defaults to a dry run and requires `--apply` to write.
- **`rac/cli.py`** — thin Typer CLI (`rac init`, `rac validate`, `rac rank`, `rac render`, `rac ingest`) wiring the above together. `_require_valid` is a shared helper (used by `rank`/`render`, not `validate` itself, which has its own richer warnings+errors output) that blocks a command when the graph has ERROR-severity issues. Most commands listed in `rsm_spec.md`'s CLI section (`build`, `export`, `lint`, `doctor`, `search`, etc.) are not yet implemented.

### Key invariants to preserve when touching entities/validation

- **Person is the sole aggregate root**; Organization, Competency, and Artifact are shared/referenced entities living outside the ownership tree (top-level, pointed to but never contained).
- **A Claim has exactly one owning container** — `Position` (via `position_id`) or `Person` directly (`position_id=None`), never both, never neither.
- **Entity ids are globally unique across the whole `ResumeDocument`**, not just within their own type's list — `_check_unique_ids` in `validation.py` exists specifically because dict-keyed indices in `ResumeGraph` silently drop data on an id collision (last write wins), so uniqueness must be checked independent of and before those indices are trusted.
- Adding a new relationship or entity type is a spec change, not just a code change — `rsm_spec.md` §8 declares the graph closed-world (only enumerated relationship types may exist); update the spec first.
