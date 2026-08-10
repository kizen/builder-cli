"""`kizen apply` — consume a plan from stdin or --plan-file and execute it."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.prompt import Confirm

from kizen_builder.cli._mutations import _render_result
from kizen_builder.cli._shared import app, cli_errors, console, err_console
from kizen_builder.tools import plans as plan_tools


@app.command("apply")
def apply_cmd(
    plan_file: str = typer.Option(
        "", "--plan-file", help="Path to a plan JSON file. Default: read from stdin."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the y/N confirmation prompt."
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit results as JSON."),
) -> None:
    """Apply a saved plan (the JSON a mutation verb emits with --dry-run --json).

    Reads the plan JSON from `--plan-file` or stdin. Confirms with the user
    (unless `--yes`), executes operations, prints results.
    """
    if plan_file:
        text = Path(plan_file).read_text()
    else:
        if sys.stdin.isatty():
            err_console.print(
                "[red]error:[/red] no plan provided. "
                "Pipe a plan JSON to stdin or pass --plan-file."
            )
            raise typer.Exit(code=2)
        text = sys.stdin.read()

    try:
        plan = plan_tools.plan_from_json(text)
    except Exception as e:  # noqa: BLE001
        err_console.print(f"[red]error parsing plan:[/red] {e}")
        raise typer.Exit(code=2) from e

    if not json_out:
        console.print(f"[bold]Apply plan {plan.id}[/bold]  [dim]→ {plan.env}[/dim]")
        console.print(plan.summary)
        for op in plan.operations:
            console.print(f"  • {op.action} {op.kind}: {op.key}")
    if not yes and not Confirm.ask(
        f"Apply {len(plan.operations)} op(s)?", default=False
    ):
        console.print("[yellow]aborted[/yellow]")
        raise typer.Exit(code=1)

    with cli_errors():
        result = plan_tools.apply_plan(plan)

    if json_out:
        typer.echo(plan_tools.result_to_json(result))
    else:
        _render_result(result)
    if not result.all_ok:
        raise typer.Exit(code=1)
