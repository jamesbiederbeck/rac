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
```

`rac rank` talks to a text-embedding HTTP service when a profile has a `query`; it defaults to the author's homelab instance (`http://chiclets.lan:8081`, overridable via `RAC_EMBEDDING_URL`) and is not reachable from arbitrary environments — profiles without `query` don't need it.

There is no configured linter/formatter/type-checker in `pyproject.toml` — don't assume `ruff`/`mypy`/`black` are wired up unless you check first.

## Architecture

Three layers, each with a distinct responsibility and file:

- **`rac/model.py`** — the RSM as pydantic data. All entities and value objects are frozen/immutable (`ConfigDict(frozen=True, extra="forbid")`): a build consumes one snapshot; edits produce a new set of objects, never in-place mutation. `ResumeDocument` is the flat, storage-independent bag of all entities for one Person (what storage adapters read/write). Per-entity/local invariants (non-empty text, date ordering, produced/referenced disjointness on a single Claim) are enforced here via pydantic `model_validator`s, because pydantic raises `ValidationError` at construction time.
- **`rac/graph.py`** — `ResumeGraph.build(document)` turns the flat `ResumeDocument` into an index-backed view: id→entity lookups and reverse indices (claims by position, evidence by claim, etc.), plus the derived properties from RSM §10 (`claim_count_for_competency`, `reference_count_for_artifact`, `effective_confidence`). It performs no validation — it assumes the document may be invalid and builds indices anyway, deliberately, so the validator can inspect a graph built from bad data.
- **`rac/validation.py`** — everything that requires seeing the *whole graph* rather than one entity: referential integrity (dangling `ref(Entity)` ids), global uniqueness, cardinality (at most one open-ended Position), the position-overlap rules, competency/organization normalization, orphan detection. Returns a flat `list[Issue]` tagged `Severity.ERROR` or `Severity.WARNING` — never raises. The error/warning split for each rule is spec-defined in `rsm_spec.md`, not a judgment call to make locally (e.g. overlapping positions is a warning unless both are full-time at different orgs, which is an error).
- **`rac/storage/`** — `StorageAdapter` (`base.py`) is the abstract load/save interface; `YamlStorageAdapter` is the only implementation so far, storing the full `ResumeDocument` as one YAML file with relationships expressed as id references. Additional backends (SQLite, remote API — see `project_plan.md`) should implement the same interface without changing what a `ResumeDocument` means.
- **`rac/profile.py`** — `BuildProfile` (the filtering/weighting config from `project_plan.md`'s "Build Profiles" section: `filters.include_tags`/`exclude_tags`, `weights` keyed by Competency name, plus a `query` field for embedding-based ranking). `filter_claims` applies tag filters; `score_by_weights` is the non-embedding fallback score (Claim.importance × average matching competency weight); `apply_profile` ties both together, using embedding similarity as the primary score when `query` + an `EmbeddingProvider` are supplied. `theme`/`page_limit` are accepted (spec fields) but unused — no renderer exists yet.
- **`rac/ranking.py`** — `rank_claims_by_query` scores Claims by cosine similarity between their text and a free-text prompt, via an `EmbeddingProvider` (deduping identical Claim text before embedding). Pure-Python cosine similarity, no numpy — vectors from the embedding service are not assumed pre-normalized.
- **`rac/embedding.py`** — `EmbeddingProvider` is the `Protocol` consumed by `ranking.py`; `EmbeddingClient` is the concrete HTTP implementation, talking to a `/vectors`-style embeddings-proxy (default `http://chiclets.lan:8081`, override via `RAC_EMBEDDING_URL`). Tests use a fake provider (`tests/conftest.py`) instead of hitting the network.
- **`rac/cli.py`** — thin Typer CLI (`rac init`, `rac validate`, `rac rank`) wiring the above together. Most commands listed in `rsm_spec.md`'s CLI section (`build`, `render`, `export`, `lint`, `doctor`, `search`, etc.) are not yet implemented.

### Key invariants to preserve when touching entities/validation

- **Person is the sole aggregate root**; Organization, Competency, and Artifact are shared/referenced entities living outside the ownership tree (top-level, pointed to but never contained).
- **A Claim has exactly one owning container** — `Position` (via `position_id`) or `Person` directly (`position_id=None`), never both, never neither.
- **Entity ids are globally unique across the whole `ResumeDocument`**, not just within their own type's list — `_check_unique_ids` in `validation.py` exists specifically because dict-keyed indices in `ResumeGraph` silently drop data on an id collision (last write wins), so uniqueness must be checked independent of and before those indices are trusted.
- Adding a new relationship or entity type is a spec change, not just a code change — `rsm_spec.md` §8 declares the graph closed-world (only enumerated relationship types may exist); update the spec first.
