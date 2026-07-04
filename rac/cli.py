from __future__ import annotations

from pathlib import Path

import typer
from pydantic import ValidationError

from rac.graph import ResumeGraph
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


if __name__ == "__main__":
    app()
