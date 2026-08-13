"""`kizen objects` — reads cover custom and built-in objects; create/update/delete are custom-only."""

from __future__ import annotations

from typing import Any

import typer
from rich.table import Table

from kizen_builder import output as out
from kizen_builder.cli._mutations import _run_mutation
from kizen_builder.cli._shared import (
    JSON_OPTION,
    OUTPUT_OPTION,
    app,
    cli_errors,
    console,
    err_console,
)
from kizen_builder.tools import objects as obj_tools
from kizen_builder.tools.planners import objects as object_planners

objects_app = typer.Typer(
    help="Read objects, custom and built-in; create, update, and delete custom objects.",
    no_args_is_help=True,
)
app.add_typer(objects_app, name="objects")


@objects_app.command("list")
def objects_list(
    output: str = OUTPUT_OPTION,
    json_out: bool = JSON_OPTION,
) -> None:
    """List objects in the configured env, custom and built-in (e.g. Contacts)."""
    fmt = out.resolve_format(output, json_out)
    with cli_errors():
        items = obj_tools.list_objects()

    def table() -> None:
        t = Table(title="Objects")
        t.add_column("api_name")
        t.add_column("display_name")
        t.add_column("entity_name")
        t.add_column("id")
        for o in items:
            t.add_row(
                o["api_name"] or "",
                o["display_name"] or "",
                o["entity_name"] or "",
                (o["id"] or ""),
            )
        console.print(t)

    out.render(
        fmt,
        json_data=items,
        table=table,
        csv_rows=items,
        csv_columns=[
            out.Column("api_name", "api_name"),
            out.Column("display_name", "display_name"),
            out.Column("entity_name", "entity_name"),
            out.Column("id", "id"),
        ],
    )


@objects_app.command("get")
def objects_get(
    api_name: str = typer.Argument(..., help="Object api_name."),
    output: str = OUTPUT_OPTION,
    json_out: bool = JSON_OPTION,
) -> None:
    """Show one object plus its categories and fields.

    CSV emits the field list (one row per field) — the object header and
    category summary are table/JSON only.
    """
    fmt = out.resolve_format(output, json_out)
    with cli_errors(LookupError):
        result = obj_tools.get_object(api_name)

    cat_by_id = {c["id"]: c["name"] for c in result["categories"]}

    def table() -> None:
        console.print(
            f"[bold]{result['display_name']}[/bold]  "
            f"[dim]({result['api_name']}, id={result['id']})[/dim]"
        )
        cat_table = Table(title="Categories")
        cat_table.add_column("name")
        cat_table.add_column("id")
        for c in result["categories"]:
            cat_table.add_row(c["name"] or "", (c["id"] or ""))
        console.print(cat_table)

        fld_table = Table(title="Fields")
        fld_table.add_column("api_name")
        fld_table.add_column("display_name")
        fld_table.add_column("type")
        fld_table.add_column("target", style="dim")
        fld_table.add_column("category")
        fld_table.add_column("id")
        for f in result["fields"]:
            target = f.get("relation_target") or ""
            card = f.get("relation_cardinality") or ""
            target_cell = f"{target} ({card})" if target and card else target
            fld_table.add_row(
                f["api_name"] or "",
                f["display_name"] or "",
                f["field_type"] or "",
                target_cell,
                cat_by_id.get(f["category_id"], "") or "",
                (f["id"] or ""),
            )
        console.print(fld_table)

        if result.get("stages") is not None:
            stg_table = Table(title="Stages")
            stg_table.add_column("order", justify="right")
            stg_table.add_column("name")
            stg_table.add_column("status")
            stg_table.add_column("chance to close", justify="right")
            stg_table.add_column("id")
            for s in result["stages"]:
                pct = s.get("percentage_chance_to_close")
                stg_table.add_row(
                    str(s.get("order") if s.get("order") is not None else ""),
                    s.get("name") or "",
                    s.get("status") or "",
                    f"{pct}%" if pct is not None else "",
                    s.get("id") or "",
                )
            console.print(stg_table)

    out.render(
        fmt,
        json_data={k: v for k, v in result.items() if k != "raw"},
        table=table,
        csv_rows=result["fields"],
        csv_columns=[
            out.Column("api_name", "api_name"),
            out.Column("display_name", "display_name"),
            out.Column("field_type", "field_type"),
            out.Column("relation_target", "relation_target"),
            out.Column("relation_cardinality", "relation_cardinality"),
            out.Column("category", lambda f: cat_by_id.get(f.get("category_id"), "")),
            out.Column("id", "id"),
        ],
    )


# ---------------------------------------------------------------------------
# objects create/update
# ---------------------------------------------------------------------------


@objects_app.command("create")
def objects_create(
    api_name: str = typer.Option(
        ..., "--api-name", help="Object api_name (e.g. 'invoice')."
    ),
    name: str = typer.Option(
        ..., "--name", help="Display name (plural, e.g. 'Invoices')."
    ),
    entity_name: str = typer.Option(
        "",
        "--entity-name",
        help="Singular form (e.g. 'Invoice'). Defaults to display name.",
    ),
    description: str = typer.Option("", "--description", help="Object description."),
    object_type: str = typer.Option(
        "standard",
        "--object-type",
        help="Object type: 'standard' (default) or 'pipeline' (stage-based object).",
    ),
    pipeline: bool = typer.Option(
        False, "--pipeline", help="Shorthand for --object-type pipeline."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show the plan without applying."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the y/N confirmation prompt."
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Emit JSON (plan with --dry-run, results otherwise)."
    ),
) -> None:
    """Create one custom object (no fields/categories yet).

    `--pipeline` (or `--object-type pipeline`) creates a stage-based
    pipeline object; the default is a standard object. Kizen requires at
    least one stage to create a pipeline object, so this seeds a single
    placeholder "Open" stage — use `objects stages create/update` to add
    the real ones afterward.
    """
    resolved_type = "pipeline" if pipeline else object_type
    if resolved_type not in ("standard", "pipeline"):
        err_console.print(
            f"[red]error:[/red] --object-type must be 'standard' or 'pipeline' "
            f"(got {resolved_type!r})."
        )
        raise typer.Exit(code=2)
    obj_dict: dict[str, Any] = {
        "api_name": api_name,
        "name": name,
        "object_type": resolved_type,
    }
    if entity_name:
        obj_dict["entity_name"] = entity_name
    if description:
        obj_dict["description"] = description

    _run_mutation(
        lambda: object_planners.plan_create_object(obj_dict),
        dry_run=dry_run,
        yes=yes,
        json_out=json_out,
    )


@objects_app.command("update")
def objects_update(
    object_api_name: str = typer.Argument(..., help="Object api_name to update."),
    object_name: str = typer.Option(
        "", "--object-name", help="New display name (plural)."
    ),
    entity_name: str = typer.Option("", "--entity-name", help="New singular form."),
    description: str = typer.Option("", "--description", help="New description."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show the plan without applying."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the y/N confirmation prompt."
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Emit JSON (plan with --dry-run, results otherwise)."
    ),
) -> None:
    """Update one custom object. Only the flags you set are changed."""
    changes: dict[str, Any] = {}
    if object_name:
        changes["object_name"] = object_name
    if entity_name:
        changes["entity_name"] = entity_name
    if description:
        changes["description"] = description

    _run_mutation(
        lambda: object_planners.plan_update_object(object_api_name, changes),
        dry_run=dry_run,
        yes=yes,
        json_out=json_out,
    )


@objects_app.command("delete")
def objects_delete(
    object_api_name: str = typer.Argument(..., help="Object api_name to delete."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show the plan without applying."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the y/N confirmation prompt."
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Emit JSON (plan with --dry-run, results otherwise)."
    ),
) -> None:
    """Delete (archive) one custom object. Removes its data across all records."""
    _run_mutation(
        lambda: object_planners.plan_delete_object(object_api_name),
        dry_run=dry_run,
        yes=yes,
        json_out=json_out,
    )
