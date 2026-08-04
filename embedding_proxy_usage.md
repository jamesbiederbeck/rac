# Embedding proxy usage

Handoff note on the text-embedding service `rac` talks to. Source lives at
`~/code/ml/embeddings/embeddings-proxy` (git.hiddencove.xyz/victor/embeddings-proxy); read its
`CLAUDE.md` for full details if you need more than this summary.

## What it is

A small FastAPI proxy in front of an embedding backend. It caches every embedded vector in Redis
(keyed by a hash of backend+model+text, so identical text is never re-embedded) and, if configured,
also upserts vectors into Qdrant for nearest-neighbour search. Deployed on the author's homelab Pi
(`chiclets.lan`) — not reachable from arbitrary environments (no auth, no public exposure).

## How `rac` uses it today

Only one endpoint, only one field: `rac/embedding.py`'s `EmbeddingClient.embed()` does

```
POST {base_url}/vectors   {"text": "..."}   ->   {"vector": [floats], ...}
```

`base_url` defaults to `http://chiclets.lan:8081`, overridable via `RAC_EMBEDDING_URL`. This is
consumed by `rac/ranking.py` (`rank_claims_by_query`, cosine similarity, no numpy) via the
`EmbeddingProvider` protocol, wired into `BuildProfile.apply_profile` when a profile has a `query`.
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
- **`POST /search {"text", "top_k"}`** — embeds the query (Redis-cached) and returns nearest
  neighbours from Qdrant, response shaped like a LangChain `Document`:
  ```json
  {"query": "...", "results": [{"page_content": "...", "metadata": {...}, "score": 0.82}, ...]}
  ```
  Returns `501` if the target instance has no vector store configured — don't assume every
  deployment of this proxy supports search. As of 2026-07-16 this response shape (`query`/
  `page_content`/`metadata`/`score`) is not yet in a tagged release — check the proxy's CHANGELOG/
  git tags before depending on the exact field names in production code.
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
- Not reachable outside the homelab network — any CI or test environment must use the fake
  `EmbeddingProvider`, never the real client.
