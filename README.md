# rac — Resume-as-Code

A declarative resume generation system: content, presentation, and build
configuration are kept separate, the way infrastructure-as-code or a static
site generator would treat them.

- **Content is canonical.** Your professional history lives as structured
  data (the Resume Semantic Model, or RSM) — not as a Word doc, not as
  Markdown with your formatting baked in.
- **Build profiles determine what's included.** Filter and rank Claims by
  tag, competency weight, or a free-text query (e.g. "target this JD"),
  without duplicating your resume per application.
- **Rendering is a projection.** The same content produces Markdown, HTML,
  a browsable web page, or a page-limited PDF.
- **AI edits semantics, not formatting.** Ingesting a PDF or an LLM-assisted
  rewrite touches the underlying Claims, never hand-tweaked prose in a
  rendered document.

## The Resume Semantic Model (RSM)

The RSM is a typed, closed-world graph of the professional claims made about
one candidate: `Person` is the sole aggregate root; `Position`s belong to it;
`Claim`s belong to a `Position` or to the `Person` directly; `Organization`,
`Competency`, and `Artifact` are shared entities referenced from claims.
Storage (YAML today; SQLite or a remote API are valid future backends),
validation, ranking, and rendering all consume this one model — none of them
define it.

The full spec is normative and lives in [`rsm_spec.md`](rsm_spec.md); the
broader system architecture and roadmap is in
[`project_plan.md`](project_plan.md). Only a slice of `project_plan.md` is
implemented so far — see [Status](#status) below.

## Quick start

```bash
pip install -e ".[dev]"

rac init resume.yaml --name "Jane Doe"       # or start from examples/sample_resume.yaml
rac validate resume.yaml                     # check it against the RSM
rac render resume.yaml --format markdown     # print a Markdown resume
```

There's a runnable example already: `examples/sample_resume.yaml` +
`examples/sample_profile.yaml`.

```bash
rac render examples/sample_resume.yaml --format html --profile examples/sample_profile.yaml
```

## Commands

```bash
rac init resume.yaml --name "Jane Doe"     # create a starter YAML resume
rac validate resume.yaml                   # validate a resume file against the RSM
rac rank resume.yaml profile.yaml          # filter + rank Claims per a build profile
rac render resume.yaml --format markdown|html|web|pdf [--profile profile.yaml] [--output path]
rac render resume.yaml --format html|pdf --theme jsonresume-theme-NAME [--node-modules path] [--print-css overrides.css] [--pdf-engine weasyprint|chrome]
rac ingest resume.pdf --into resume.yaml [--extracted extracted.json] [--apply]
```

### Build profiles

A build profile (see `examples/sample_profile.yaml`) filters Claims by tag,
weights them by Competency, and optionally ranks them by embedding
similarity to a free-text `query` — useful for tailoring which Claims
surface first for a specific role, without hand-editing your resume per
application. `rac rank` and `--profile` on `rac render` both consume it.

Embedding-based ranking (`query`) talks to an external text-embedding HTTP
service (see [embedding_proxy_usage.md](embedding_proxy_usage.md) for the
expected API shape) via `RAC_EMBEDDING_URL`. It's entirely optional — a
profile without `query` falls back to tag filters and competency weights
alone, no network call involved. The author's own
[`embeddings-proxy`](https://github.com/jamesbiederbeck/embeddings-proxy)
project is a compatible implementation if you want to run your own.

### Rendering

Markdown and HTML render directly from the RSM. `--format pdf` requires the
optional `pdf` extra (`pip install -e ".[pdf]"`, pulls in WeasyPrint) and
supports `--page-limit N`, which trims the lowest-priority Claims until the
PDF fits. Regardless of `--profile`, only public-visibility Claims are ever
rendered — draft/private Claims never leak into shared output.

#### JSON Resume themes

`rac render --format html|pdf --theme jsonresume-theme-NAME` renders through
any installed [JSON Resume](https://jsonresume.org) theme instead of rac's
own built-in HTML template. rac projects the RSM into the (lossy) JSON
Resume schema and shells out to the theme's npm package, so you'll need
Node.js plus `npm install jsonresume-theme-NAME` (or point `--node-modules`
at wherever it's installed) — themes are a runtime dependency only, never a
Python one.

```bash
npm install jsonresume-theme-caffeine
rac render resume.yaml --format html --theme jsonresume-theme-caffeine
```

Two separate print problems show up with JSON Resume themes, and
`--print-css`/`--pdf-engine` address different ones:

- **WeasyPrint-specific rendering gaps.** Themes are authored and tested
  against a browser, and printing them through WeasyPrint (rac's default
  PDF engine) can misrender browser-only CSS like floats or percentage
  heights spanning a page break. `--pdf-engine chrome` sidesteps this
  entirely by printing through headless Chrome (via a local
  `npm install puppeteer`) instead — the actual engine themes are built
  against — so it usually needs no further tweaking.
- **Themes with no print stylesheet at all.** Plenty of themes are designed
  screen-first and never set `break-inside`/`page-break-inside` on their
  entries, so *any* print engine (Chrome's own Ctrl+P included, not just
  WeasyPrint) will split a job entry awkwardly across a page boundary.
  `examples/print-overrides/generic.css` is a theme-agnostic fix for this:
  it adds `break-inside: avoid` to list items/rows, `break-after: avoid` to
  headings, and disables floats for print — the same properties that make
  `jsonresume-theme-consultant-polished-printable` print cleanly where its
  sibling `jsonresume-theme-consultant-polished` (identical layout, no
  print rules) doesn't.
  `examples/print-overrides/jsonresume-theme-caffeine.css` is a worked
  example of the theme-specific alternative, for when a theme's own float
  layout needs more surgical fixes than the generic rules cover.

`--print-css` injects the chosen stylesheet after the theme's own, so its
rules win the cascade without touching the theme's source:

```bash
rac render resume.yaml --format html --theme jsonresume-theme-eloquent \
  --print-css examples/print-overrides/generic.css
```

```bash
npm install puppeteer
rac render resume.yaml --format pdf --theme jsonresume-theme-caffeine --pdf-engine chrome
```

### Ingesting a resume PDF

`rac ingest` turns an existing resume PDF into RSM data and merges it into a
YAML resume without duplicating Positions/Claims that already exist under
different wording (dedup is by exact text match, then, if an embedding
service is configured, by similarity). Every add/skip/ambiguous match is
reported; nothing is written unless you pass `--apply`.

`rac ingest` needs structured JSON before it can merge anything. Two ways to
get it:

- **Outside Claude Code**: pass nothing extra — it calls an OpenAI-compatible
  LLM API (`RAC_LLM_API_KEY`/`RAC_LLM_MODEL`, defaults to OpenRouter) to
  structure the extracted PDF text itself.
- **Inside Claude Code**: use the bundled [`ingest-resume`](.claude/skills/ingest-resume/SKILL.md)
  skill instead. It does the structuring agentically — no API key needed —
  and hands the result to `rac ingest --extracted`.

PDF text extraction shells out to `pdftotext` (poppler-utils); scanned/
image-only PDFs aren't supported.

## Status

Implemented: the RSM core model, YAML storage, validation, build profiles
(tag filtering + competency weighting + optional embedding-based ranking),
Markdown/HTML/web/PDF rendering with page-limit trimming, JSON Resume theme
rendering (with a WeasyPrint or headless-Chrome PDF backend), and PDF ingest
with merge/dedup.

Not yet implemented (see `project_plan.md`): a Theme system (rendering
currently ships one built-in look), SQLite/remote storage backends, and most
of the broader CLI surface (`build`, `export`, `lint`, `doctor`, `search`).

## Development

```bash
pip install -e ".[dev]"
pytest                          # run all tests
pytest tests/test_model.py      # run one file
pytest -k overlap               # run tests matching a keyword
```

See [`CLAUDE.md`](CLAUDE.md) for a fuller architecture walkthrough if you're
working on the codebase itself.
