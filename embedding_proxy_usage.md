# Embedding proxy usage

`rac` optionally talks to a small external text-embedding HTTP service — a companion project of
the author's, `embeddings-proxy` (not yet published) — for anything that needs semantic
similarity: profile-query ranking and fuzzy dedup during ingest. Nothing in `rac` requires it;
every consumer degrades gracefully (see below) when it's unset or unreachable. Any service
speaking its `/vectors` contract below works equally well.

## What it is

A small FastAPI proxy in front of one or more embedding backends (transformers-inference, OpenAI,
llama.cpp). It caches every embedded vector in Redis (keyed by a hash of backend+model+text, so
identical text is never re-embedded) and, if configured, also upserts vectors into Qdrant for
nearest-neighbour search. `rac` only ever calls its plain embedding endpoint — it never touches
the Qdrant/search side.

## Running your own instance

`rac` doesn't vendor or require any particular deployment of this — point it at any service that
implements the `/vectors` contract below. The author's own `embeddings-proxy` (FastAPI + Redis
cache in front of a transformers-inference/OpenAI/llama.cpp backend, with a
`docker compose up`-able stack) is one such implementation, once published; until then, anything
speaking the same contract — including a thin wrapper around an OpenAI-compatible embeddings
endpoint — works as a drop-in.

```bash
export RAC_EMBEDDING_URL=http://localhost:8081   # wherever your instance is listening
```

## How `rac` uses it today

One endpoint, one field: `rac/embedding.py`'s `EmbeddingClient.embed()` does

```
POST {base_url}/vectors   {"text": "..."}   ->   {"vector": [floats], ...}
```

`base_url` defaults to `http://chiclets.lan:8081` (the author's own instance — not reachable
outside that network; point `RAC_EMBEDDING_URL` at your own instance instead), overridable via
`RAC_EMBEDDING_URL`. Two independent callers reach it through the `EmbeddingProvider` protocol:

- **`rac/ranking.py`** (`rank_claims_by_query`, cosine similarity, no numpy) — wired into
  `BuildProfile.apply_profile` when a profile has a `query`; used by `rac rank` and `rac render
  --profile`.
- **`rac/ingest/resolve.py`** — fuzzy title/Claim-text matching during `rac ingest`, so a
  reworded achievement or a slightly-retitled Position doesn't get merged as a duplicate. Falls
  back to exact-text-match-only dedup if the service is unreachable (`resolve_extracted_resume`
  catches `httpx.HTTPError` and retries with `embedding_provider=None`; `rac ingest` prints a note
  when this happens).

Tests use a fake provider (`tests/conftest.py`) instead of hitting the network — don't add tests
that require the real service to be reachable.

If you're touching `rac/embedding.py`, note it deliberately knows nothing about the RSM — keep it
a generic HTTP client, not resume-aware.

## What else the service can do (not used by `rac` yet)

These exist on the proxy now and could be relevant if `rsm_spec.md`'s planned `search` CLI command
or the SQLite storage backend's "embedding storage" idea (`project_plan.md`) get built:

- **`POST /vectors` accepts optional `metadata: dict`** — passed through to the Qdrant payload
  alongside the text if a vector store is configured. Useful if Claims ever get indexed with their
  `id`/`competency`/`position_id` etc. attached, instead of bare text.
- **`POST /search {"text", "top_k", "scope"?}`** — embeds the query (Redis-cached) and returns
  nearest neighbours from the configured vector store, response shaped like a LangChain
  `Document`:
  ```json
  {"query": "...", "results": [{"page_content": "...", "metadata": {...}, "locations": [...], "score": 0.82}, ...]}
  ```
  Returns `501` if the target instance has no vector store configured for the resolved model —
  don't assume every deployment of this proxy supports search.
- **`POST /v1/embeddings`** — OpenAI-compatible adapter (`{"input": "..."|[...], "model"?}`), same
  Redis-cache path, for OpenAI-client-compatible libraries (LangChain's `OpenAIEmbeddings`,
  LiteLLM). Not a reason to change `rac/embedding.py` — the plain `/vectors` endpoint is simpler
  for a single-text-in/single-vector-out client and does everything `rac` needs.
- **`GET /.well-known/ready`** — real dependency check (Redis + backend + Qdrant if configured),
  `503` on failure with per-check detail. Useful if `rac` ever wants a preflight check before a
  batch ranking run instead of failing mid-batch on the first `embed()` call.

## Things to watch for

- The proxy has no notion of resume/Claim semantics — everything above is generic text-in,
  vector-out. Any resume-specific meaning (which Claim a vector belongs to, etc.) has to live on
  the `rac` side, via `metadata` if/when that gets adopted.
- Cache keys are `sha256(backend:model:text)` — changing the proxy's configured backend or model
  changes what's considered "the same text," so don't assume vectors are comparable across
  differently-configured proxy instances.
- The author's own instance isn't reachable outside their home network — any CI or test
  environment must use the fake `EmbeddingProvider` (`tests/conftest.py`), never the real client.
