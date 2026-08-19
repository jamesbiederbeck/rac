from __future__ import annotations

from enum import Enum
from pathlib import Path

import httpx
import typer
from pydantic import ValidationError

from rac.embedding import EmbeddingClient, EmbeddingNotConfiguredError
from rac.graph import ResumeGraph
from rac.ingest import (
    ExtractedResume,
    ExtractionError,
    OpenAICompatibleExtractor,
    PdfExtractionError,
    extract_text,
    resolve_extracted_resume,
)
from rac.model import Claim, Visibility
from rac.profile import BuildProfile, apply_profile, load_build_profile
from rac.render import (
    ChromePdfError,
    PageLimitError,
    ThemeRenderError,
    build_resume_sections,
    fit_claims_to_page_limit,
    html_to_pdf,
    html_to_pdf_via_chrome,
    inject_css,
    order_by_importance,
    render_html,
    render_jsonresume_theme,
    render_markdown,
    render_pdf,
    render_web,
)
from rac.storage import YamlStorageAdapter
from rac.validation import Severity, validate

app = typer.Typer(add_completion=False, help="Resume-as-Code (RaC) CLI")


class RenderFormat(str, Enum):
    MARKDOWN = "markdown"
    HTML = "html"
    WEB = "web"
    PDF = "pdf"


class PdfEngine(str, Enum):
    WEASYPRINT = "weasyprint"
    CHROME = "chrome"


def _require_valid(graph: ResumeGraph, action: str) -> None:
    """Run validate() and exit 1 if any ERROR-severity issue is present.
    Shared by commands (rank, render) that need a clean graph before doing
    further work; `validate_cmd` itself has its own richer output (it also
    prints warnings) so it does not use this helper."""
    errors = [i for i in validate(graph) if i.severity == Severity.ERROR]
    if errors:
        for issue in errors:
            typer.secho(str(issue), fg=typer.colors.RED)
        typer.secho(f"Resume has validation errors; fix them before {action}.", fg=typer.colors.RED)
        raise typer.Exit(code=1)


def _apply_profile_with_fallback(graph: ResumeGraph, profile: BuildProfile) -> list[tuple[Claim, float]]:
    """apply_profile(), degrading to weight-based ranking (provider=None)
    when a profile has a `query` but no embedding service is configured or
    reachable. Embedding-based ranking is an optional enhancement, not a
    hard requirement -- see embedding_proxy_usage.md -- so neither an unset
    RAC_EMBEDDING_URL nor a network failure should block rank/render."""
    provider = None
    if profile.query:
        try:
            provider = EmbeddingClient()
        except EmbeddingNotConfiguredError:
            typer.secho(
                "No embedding service configured (RAC_EMBEDDING_URL unset); "
                "falling back to weight-based ranking for this profile's query.",
                fg=typer.colors.YELLOW,
            )

    try:
        return apply_profile(graph, profile, provider=provider)
    except httpx.HTTPError as exc:
        if provider is None:
            raise
        typer.secho(
            f"Could not reach embedding service at {provider.base_url}: {exc}; "
            "falling back to weight-based ranking.",
            fg=typer.colors.YELLOW,
        )
        return apply_profile(graph, profile, provider=None)


@app.command(name="init")
def init_cmd(
    path: Path = typer.Argument(Path("resume.yaml"), help="Path to create a starter resume file at"),
    name: str = typer.Option(..., prompt=True, help="Candidate name"),
) -> None:
    """Create a starter YAML resume file with a minimal Person entity."""
    if path.exists():
        typer.secho(f"{path} already exists; not overwriting.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    from rac.model import Person, ResumeDocument

    document = ResumeDocument(person=Person(id="person_1", name=name))
    YamlStorageAdapter().save(document, path)
    typer.secho(f"Created {path}", fg=typer.colors.GREEN)


@app.command(name="validate")
def validate_cmd(
    path: Path = typer.Argument(..., exists=True, help="Path to a YAML resume file"),
) -> None:
    """Validate a resume file against the Resume Semantic Model."""
    adapter = YamlStorageAdapter()
    try:
        document = adapter.load(path)
    except ValidationError as exc:
        typer.secho(f"Schema validation failed:\n{exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    graph = ResumeGraph.build(document)
    issues = validate(graph)

    errors = [i for i in issues if i.severity == Severity.ERROR]
    warnings = [i for i in issues if i.severity == Severity.WARNING]

    for issue in issues:
        color = typer.colors.RED if issue.severity == Severity.ERROR else typer.colors.YELLOW
        typer.secho(str(issue), fg=color)

    if not issues:
        typer.secho("No issues found.", fg=typer.colors.GREEN)

    typer.echo(f"\n{len(errors)} error(s), {len(warnings)} warning(s).")

    if errors:
        raise typer.Exit(code=1)


@app.command(name="rank")
def rank_cmd(
    resume_path: Path = typer.Argument(..., exists=True, help="Path to a YAML resume file"),
    profile_path: Path = typer.Argument(..., exists=True, help="Path to a YAML build profile"),
) -> None:
    """Filter and rank a resume's Claims according to a build profile."""
    document = YamlStorageAdapter().load(resume_path)
    profile = load_build_profile(profile_path)

    graph = ResumeGraph.build(document)
    _require_valid(graph, "ranking")

    ranked = _apply_profile_with_fallback(graph, profile)

    if not ranked:
        typer.secho("No claims matched this profile's filters.", fg=typer.colors.YELLOW)
        return

    for claim, score in ranked:
        text = claim.text if len(claim.text) <= 80 else claim.text[:77] + "..."
        typer.echo(f"{score:6.3f}  {claim.id:20s} {text}")


@app.command(name="render")
def render_cmd(
    resume_path: Path = typer.Argument(..., exists=True, help="Path to a YAML resume file"),
    format: RenderFormat = typer.Option(RenderFormat.MARKDOWN, "--format", help="Output format"),
    profile_path: Path | None = typer.Option(
        None, "--profile", exists=True, help="Optional build profile to filter/rank which Claims are included"
    ),
    page_limit: int | None = typer.Option(
        None,
        "--page-limit",
        help="Trim lowest-priority Claims until the PDF fits this many pages (--format pdf only)",
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write to this path instead of stdout (required for --format pdf)"
    ),
    theme: str | None = typer.Option(
        None,
        "--theme",
        help="Render with an installed JSON Resume theme package (e.g. jsonresume-theme-elegant) instead of "
        "rac's built-in template -- requires Node.js and `npm install <theme>`. --format html or pdf only.",
    ),
    node_modules: Path | None = typer.Option(
        None,
        "--node-modules",
        help="Directory to resolve --theme from (default: node_modules in the current directory)",
    ),
    print_css: Path | None = typer.Option(
        None,
        "--print-css",
        exists=True,
        help="CSS file injected after --theme's own styles, to override browser-only layout that WeasyPrint "
        "renders badly (e.g. floats spanning a page break). Only valid with --theme --pdf-engine weasyprint.",
    ),
    pdf_engine: PdfEngine = typer.Option(
        PdfEngine.WEASYPRINT,
        "--pdf-engine",
        help="PDF backend for --theme --format pdf: WeasyPrint (default), or headless Chrome via Puppeteer -- "
        "themes are written and tested against a browser, so `chrome` often renders a theme's layout correctly "
        "with no --print-css overrides needed, at the cost of requiring `npm install puppeteer`. Only valid "
        "with --theme.",
    ),
) -> None:
    """Render a resume to Markdown, HTML, web (sidebar-nav HTML), or PDF.

    Regardless of --profile, only public-visibility Claims are ever
    rendered -- draft/private Claims never appear in output meant to be
    shared, even if a profile's tag filters would otherwise include them.
    """
    if format == RenderFormat.PDF and output is None:
        typer.secho("--output is required for --format pdf (PDF can't be printed to a terminal).", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if theme is not None and format not in (RenderFormat.HTML, RenderFormat.PDF):
        typer.secho("--theme only applies to --format html or pdf.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if print_css is not None and theme is None:
        typer.secho("--print-css only applies alongside --theme.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if pdf_engine == PdfEngine.CHROME and theme is None:
        typer.secho("--pdf-engine chrome only applies alongside --theme.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    document = YamlStorageAdapter().load(resume_path)
    graph = ResumeGraph.build(document)
    _require_valid(graph, "rendering")

    if profile_path is not None:
        profile = load_build_profile(profile_path)
        ranked = _apply_profile_with_fallback(graph, profile)
        claims = [c for c, _ in ranked]  # already priority-ordered, highest score first
    else:
        claims = list(document.claims)
    claims = [c for c in claims if c.visibility == Visibility.PUBLIC]

    if page_limit is not None:
        if format != RenderFormat.PDF:
            typer.secho("--page-limit only applies to --format pdf; ignoring for this format.", fg=typer.colors.YELLOW)
        else:
            priority_order = claims if profile_path is not None else order_by_importance(claims)
            try:
                survivors, page_count = fit_claims_to_page_limit(graph, priority_order, page_limit)
            except ImportError:
                typer.secho('--page-limit requires the "pdf" extra: pip install -e ".[pdf]"', fg=typer.colors.RED)
                raise typer.Exit(code=1)
            except PageLimitError as exc:
                typer.secho(str(exc), fg=typer.colors.RED)
                raise typer.Exit(code=1)
            survivor_ids = {c.id for c in survivors}
            dropped = len(claims) - len(survivor_ids)
            claims = [c for c in claims if c.id in survivor_ids]  # preserve original rendering order
            if dropped:
                typer.secho(
                    f"Trimmed {dropped} claim(s) to fit {page_limit} page(s) (rendered at {page_count} page(s)).",
                    fg=typer.colors.YELLOW,
                )

    sections = build_resume_sections(graph, claims)

    content: str | bytes
    if theme is not None:
        try:
            themed_html = render_jsonresume_theme(sections, theme, node_modules=node_modules)
        except ThemeRenderError as exc:
            typer.secho(str(exc), fg=typer.colors.RED)
            raise typer.Exit(code=1)
        if print_css is not None:
            themed_html = inject_css(themed_html, print_css.read_text())
        if format == RenderFormat.HTML:
            content = themed_html
        elif pdf_engine == PdfEngine.CHROME:
            try:
                content = html_to_pdf_via_chrome(themed_html, node_modules=node_modules)
            except ChromePdfError as exc:
                typer.secho(str(exc), fg=typer.colors.RED)
                raise typer.Exit(code=1)
        else:
            try:
                content = html_to_pdf(themed_html)
            except ImportError:
                typer.secho('PDF rendering requires the "pdf" extra: pip install -e ".[pdf]"', fg=typer.colors.RED)
                raise typer.Exit(code=1)
    elif format == RenderFormat.MARKDOWN:
        content = render_markdown(sections)
    elif format == RenderFormat.HTML:
        content = render_html(sections)
    elif format == RenderFormat.WEB:
        content = render_web(sections)
    else:
        try:
            content = render_pdf(sections)
        except ImportError:
            typer.secho('PDF rendering requires the "pdf" extra: pip install -e ".[pdf]"', fg=typer.colors.RED)
            raise typer.Exit(code=1)

    if output is not None:
        if isinstance(content, bytes):
            output.write_bytes(content)
        else:
            output.write_text(content)
        typer.secho(f"Wrote {output}", fg=typer.colors.GREEN)
    else:
        typer.echo(content)


@app.command(name="ingest")
def ingest_cmd(
    pdf_path: Path = typer.Argument(..., exists=True, help="Path to a resume PDF"),
    into: Path = typer.Option(Path("resume.yaml"), "--into", help="Target YAML resume file (created if missing)"),
    extracted_path: Path | None = typer.Option(
        None,
        "--extracted",
        exists=True,
        help="Pre-extracted ExtractedResume JSON, skipping the LLM call (used by the ingest-resume skill)",
    ),
    apply: bool = typer.Option(
        False, "--apply", help="Write the merged result to --into (default is a dry-run preview only)"
    ),
) -> None:
    """Ingest a resume PDF into a YAML resume file, merging with any existing content.

    Positions are reused when they match an existing one at the same
    organization with an overlapping interval and a similar title; Claims
    are deduped against whatever's already under that Position, first by
    exact text match, then (if the embedding service is reachable) by
    similarity, so the same achievement reworded across resume versions
    doesn't get added twice. Nothing here is silent -- what was added,
    skipped, or merely flagged as a possible duplicate is always printed.
    """
    if extracted_path is not None:
        try:
            extracted = ExtractedResume.model_validate_json(extracted_path.read_text())
        except ValidationError as exc:
            typer.secho(f"{extracted_path} does not match the ExtractedResume schema:\n{exc}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
    else:
        try:
            text = extract_text(pdf_path)
        except PdfExtractionError as exc:
            typer.secho(str(exc), fg=typer.colors.RED)
            raise typer.Exit(code=1)
        try:
            extractor = OpenAICompatibleExtractor()
            extracted = extractor.extract(text)
        except (ExtractionError, httpx.HTTPError) as exc:
            typer.secho(f"Extraction failed: {exc}", fg=typer.colors.RED)
            raise typer.Exit(code=1)

    adapter = YamlStorageAdapter()
    existing = adapter.load(into) if into.exists() else None

    try:
        provider = EmbeddingClient()
    except EmbeddingNotConfiguredError:
        document, report = resolve_extracted_resume(extracted, existing, embedding_provider=None)
        report.notes.insert(0, "No embedding service configured (RAC_EMBEDDING_URL unset); fuzzy Claim dedup was skipped (exact-text-match only).")
    else:
        try:
            document, report = resolve_extracted_resume(extracted, existing, embedding_provider=provider)
        except httpx.HTTPError:
            document, report = resolve_extracted_resume(extracted, existing, embedding_provider=None)
            report.notes.insert(0, "Embedding service unreachable; fuzzy Claim dedup was skipped (exact-text-match only).")

    typer.echo(f"Extracted resume for: {extracted.name}")
    typer.echo(
        f"Added: {len(report.added_organizations)} organization(s), {len(report.added_positions)} position(s), "
        f"{len(report.added_claims)} claim(s), {len(report.added_competencies)} competenc(y/ies), "
        f"{len(report.added_credentials)} credential(s)."
    )

    if report.skipped_duplicate_claims:
        typer.echo(f"\nSkipped {len(report.skipped_duplicate_claims)} duplicate claim(s):")
        for claim_text, matched_id, score in report.skipped_duplicate_claims:
            preview = claim_text if len(claim_text) <= 70 else claim_text[:67] + "..."
            typer.echo(f"  {score:.2f}  matches {matched_id:20s} {preview}")

    if report.possible_duplicate_claims:
        typer.secho(
            f"\n{len(report.possible_duplicate_claims)} possible duplicate(s) added anyway -- review:",
            fg=typer.colors.YELLOW,
        )
        for claim_text, matched_id, score in report.possible_duplicate_claims:
            preview = claim_text if len(claim_text) <= 70 else claim_text[:67] + "..."
            typer.secho(f"  {score:.2f}  similar to {matched_id:20s} {preview}", fg=typer.colors.YELLOW)

    if report.notes:
        typer.secho("\nNotes:", fg=typer.colors.YELLOW)
        for note in report.notes:
            typer.secho(f"  - {note}", fg=typer.colors.YELLOW)

    if not apply:
        typer.echo(f"\nDry run -- not written. Re-run with --apply to write to {into}.")
        return

    graph = ResumeGraph.build(document)
    errors = [i for i in validate(graph) if i.severity == Severity.ERROR]
    if errors:
        for issue in errors:
            typer.secho(str(issue), fg=typer.colors.RED)
        typer.secho("Merged document has validation errors; not written.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    adapter.save(document, into)
    typer.secho(f"\nWrote {into}", fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()
