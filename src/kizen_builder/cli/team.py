"""`kizen team` — team-member lookup."""

from __future__ import annotations

import typer
from rich.table import Table

from kizen_builder import output as out
from kizen_builder.cli._shared import (
    JSON_OPTION,
    OUTPUT_OPTION,
    app,
    cli_errors,
    console,
)
from kizen_builder.tools import team as team_tools

team_app = typer.Typer(help="Look up team members.", no_args_is_help=True)
app.add_typer(team_app, name="team")


@team_app.command("search")
def team_search(
    name: str = typer.Argument(..., help="Name or email fragment to search for."),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results to return."),
    output: str = OUTPUT_OPTION,
    json_out: bool = JSON_OPTION,
) -> None:
    """Search team members by name or email.

    Returns id, full_name, email, and title. The id is what you pass to
    owner/assigned_to fields and scheduled activity employee_id.
    """
    fmt = out.resolve_format(output, json_out)
    with cli_errors():
        results = team_tools.search_team(name, limit=limit)

    def table() -> None:
        t = Table(title=f'Team members matching "{name}"')
        t.add_column("id", style="dim")
        t.add_column("full_name")
        t.add_column("email")
        t.add_column("title")
        for m in results:
            t.add_row(
                m.get("id") or "—",
                m.get("full_name") or "—",
                m.get("email") or "—",
                m.get("title") or "—",
            )
        console.print(t)
        if not results:
            console.print("[dim]No team members found.[/dim]")

    out.render(
        fmt,
        json_data=results,
        table=table,
        csv_rows=results,
        csv_columns=[
            out.Column("id", "id"),
            out.Column("full_name", "full_name"),
            out.Column("email", "email"),
            out.Column("title", "title"),
        ],
    )
