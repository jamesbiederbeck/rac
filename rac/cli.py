from __future__ import annotations

from pathlib import Path

import httpx
import typer
from pydantic import ValidationError

from rac.embedding import EmbeddingClient
from rac.graph import ResumeGraph
from rac.profile import apply_profile, load_build_profile
from rac.storage import YamlStorageAdapter
from rac.validation import Severity, validate

app = typer.Typer(add_completion=False, help="Resume-as-Code (RaC) CLI")


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
    errors = [i for i in validate(graph) if i.severity == Severity.ERROR]
    if errors:
        for issue in errors:
            typer.secho(str(issue), fg=typer.colors.RED)
        typer.secho("Resume has validation errors; fix them before ranking.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

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


if __name__ == "__main__":
    app()
