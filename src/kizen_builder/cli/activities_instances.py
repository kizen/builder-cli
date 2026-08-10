"""`kizen activities logged` / `scheduled` — activity instances (read-only)."""

from __future__ import annotations

import json

import typer
from rich.table import Table

from kizen_builder import output as out
from kizen_builder.cli._shared import (
    JSON_OPTION,
    OUTPUT_OPTION,
    _short,
    cli_errors,
    console,
)
from kizen_builder.cli.activities import _resolve_object_id, activities_app
from kizen_builder.tools import activities as act_tools

act_logged_app = typer.Typer(
    help="Read logged activity instances (read-only).", no_args_is_help=True
)
activities_app.add_typer(act_logged_app, name="logged")


@act_logged_app.command("get")
def act_logged_get(
    logged_id: str = typer.Argument(..., help="Logged-activity UUID."),
    output: str = OUTPUT_OPTION,
    json_out: bool = JSON_OPTION,
) -> None:
    """Show one logged activity instance with its field values."""
    fmt = out.resolve_format(output, json_out)
    with cli_errors():
        result = act_tools.get_logged_activity(logged_id)

    def table() -> None:
        console.print(
            f"[bold]{result.get('activity_name')}[/bold]  [dim](logged {result.get('id')})[/dim]"
        )
        meta = [
            f"logged_at={result.get('logged_at')}",
            f"logged_by={result.get('logged_by')}",
            f"completed_at={result.get('completed_at')}",
        ]
        console.print("[dim]" + "  ".join(str(m) for m in meta) + "[/dim]")
        ents = result.get("associated_entities") or []
        if ents:
            console.print(
                "[dim]associated: "
                + ", ".join(
                    f"{e.get('display_name')} ({e.get('object_api_name')})"
                    for e in ents
                )
                + "[/dim]"
            )
        if result.get("notes"):
            console.print(f"notes: {result['notes']}")
        t = Table(title="Field values")
        t.add_column("field", style="dim")
        t.add_column("type", style="dim")
        t.add_column("value")
        for f in result.get("fields") or []:
            val = f.get("value")
            t.add_row(
                f.get("display_name") or f.get("api_name") or "",
                f.get("field_type") or "",
                json.dumps(val) if isinstance(val, (dict, list)) else str(val),
            )
        console.print(t)

    out.render(
        fmt,
        json_data={k: v for k, v in result.items() if k != "raw"},
        table=table,
        csv_rows=result.get("fields") or [],
        csv_columns=[
            out.Column("api_name", "api_name"),
            out.Column("display_name", "display_name"),
            out.Column("field_type", "field_type"),
            out.Column("value", lambda f: json.dumps(f.get("value"))),
        ],
    )


@act_logged_app.command("list")
def act_logged_list(
    identifier: str = typer.Argument(..., help="Activity api_name or UUID."),
    obj: str = typer.Option(
        "", "--object", help="Filter by custom object api_name (or UUID)."
    ),
    search: str = typer.Option("", "--search", help="Filter by text."),
    output: str = OUTPUT_OPTION,
    json_out: bool = JSON_OPTION,
) -> None:
    """List logged instances of one activity type."""
    fmt = out.resolve_format(output, json_out)
    with cli_errors(LookupError):
        object_id = _resolve_object_id(obj) if obj else None
        items = act_tools.list_logged(
            identifier, custom_object_id=object_id, search=search or None
        )

    def table() -> None:
        t = Table(title=f"Logged instances — {identifier}")
        t.add_column("id")
        t.add_column("logged_at")
        t.add_column("logged_by")
        t.add_column("associated")
        for r in items:
            t.add_row(
                r.get("id") or "",
                str(r.get("logged_at") or ""),
                str(r.get("logged_by") or ""),
                _short(r.get("associated") or "", 50),
            )
        console.print(t)

    out.render(
        fmt,
        json_data=items,
        table=table,
        csv_rows=items,
        csv_columns=[
            out.Column("id", "id"),
            out.Column("logged_at", "logged_at"),
            out.Column("logged_by", "logged_by"),
            out.Column("associated", "associated"),
        ],
    )


act_scheduled_app = typer.Typer(
    help="Read scheduled activity instances (read-only).", no_args_is_help=True
)
activities_app.add_typer(act_scheduled_app, name="scheduled")


@act_scheduled_app.command("list")
def act_scheduled_list(
    activity: str = typer.Option(
        "", "--activity", help="Filter by activity api_name or UUID."
    ),
    assigned_to_me: bool = typer.Option(
        False, "--mine", help="Only those assigned to me."
    ),
    completed: bool | None = typer.Option(
        None, "--completed/--pending", help="Filter by completion state."
    ),
    output: str = OUTPUT_OPTION,
    json_out: bool = JSON_OPTION,
) -> None:
    """List scheduled activity instances."""
    fmt = out.resolve_format(output, json_out)
    with cli_errors(LookupError):
        items = act_tools.list_scheduled(
            activity=activity or None,
            assigned_to_me=True if assigned_to_me else None,
            completed=completed,
        )

    def table() -> None:
        t = Table(title="Scheduled activities")
        t.add_column("id")
        t.add_column("activity")
        t.add_column("due")
        t.add_column("completed_at")
        t.add_column("associated")
        for s in items:
            t.add_row(
                s.get("id") or "",
                str(s.get("activity_object") or ""),
                str(s.get("due_datetime") or ""),
                str(s.get("completed_at") or ""),
                _short(s.get("associated") or "", 40),
            )
        console.print(t)

    out.render(
        fmt,
        json_data=items,
        table=table,
        csv_rows=items,
        csv_columns=[
            out.Column("id", "id"),
            out.Column("activity_object", "activity_object"),
            out.Column("due_datetime", "due_datetime"),
            out.Column("completed_at", "completed_at"),
            out.Column("associated", "associated"),
        ],
    )


@act_scheduled_app.command("get")
def act_scheduled_get(
    scheduled_id: str = typer.Argument(..., help="Scheduled-activity UUID."),
    output: str = OUTPUT_OPTION,
    json_out: bool = JSON_OPTION,
) -> None:
    """Show one scheduled activity instance."""
    fmt = out.resolve_format(output, json_out)
    with cli_errors():
        result = act_tools.get_scheduled(scheduled_id)

    def table() -> None:
        console.print(f"[bold]scheduled activity[/bold] [dim]{result.get('id')}[/dim]")
        console.print_json(
            json.dumps({k: v for k, v in result.items() if k != "env"}, default=str)
        )

    out.render(
        fmt,
        json_data=result,
        table=table,
        csv_rows=[result],
        csv_columns=[
            out.Column("id", "id"),
            out.Column("due_datetime", "due_datetime"),
            out.Column("completed_at", "completed_at"),
        ],
    )
