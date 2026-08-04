from __future__ import annotations

from enum import Enum
from pathlib import Path

import httpx
import typer
from pydantic import ValidationError

from rac.embedding import EmbeddingClient
from rac.graph import ResumeGraph
from rac.model import Visibility
from rac.profile import apply_profile, load_build_profile
from rac.render import (
    PageLimitError,
    build_resume_sections,
    fit_claims_to_page_limit,
    order_by_importance,
    render_html,
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

    provider = EmbeddingClient() if profile.query else None

    try:
        ranked = apply_profile(graph, profile, provider=provider)
    except httpx.HTTPError as exc:
        typer.secho(f"Could not reach embedding service at {provider.base_url}: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

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
) -> None:
    """Render a resume to Markdown, HTML, web (sidebar-nav HTML), or PDF.

    Regardless of --profile, only public-visibility Claims are ever
    rendered -- draft/private Claims never appear in output meant to be
    shared, even if a profile's tag filters would otherwise include them.
    """
    if format == RenderFormat.PDF and output is None:
        typer.secho("--output is required for --format pdf (PDF can't be printed to a terminal).", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    document = YamlStorageAdapter().load(resume_path)
    graph = ResumeGraph.build(document)
    _require_valid(graph, "rendering")

    if profile_path is not None:
        profile = load_build_profile(profile_path)
        provider = EmbeddingClient() if profile.query else None
        try:
            ranked = apply_profile(graph, profile, provider=provider)
        except httpx.HTTPError as exc:
            typer.secho(f"Could not reach embedding service: {exc}", fg=typer.colors.RED)
            raise typer.Exit(code=1) from exc
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
    if format == RenderFormat.MARKDOWN:
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


if __name__ == "__main__":
    app()
