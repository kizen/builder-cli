"""`kizen automations` — reads (list/get/show/round-trip), `start`, and the
modification/failure diagnostics. Mutations live in `automations_write`.
"""

from __future__ import annotations

import json
from typing import Any

import typer
from pydantic import ValidationError
from rich.table import Table

from kizen_builder import output as out
from kizen_builder.cli._mutations import _read_spec
from kizen_builder.cli._shared import (
    JSON_OPTION,
    OUTPUT_OPTION,
    app,
    cli_errors,
    console,
    err_console,
)
from kizen_builder.tools import automations as auto_tools
from kizen_builder.tools import steps as step_tools
from kizen_builder.tools.planners import automations as auto_planners
from kizen_builder.tools.plans import PlanError

autos_app = typer.Typer(
    help="Read, create, update, and run automations.", no_args_is_help=True
)
app.add_typer(autos_app, name="automations")


@autos_app.command("list")
def autos_list(
    folder: str = typer.Option(
        "", "--folder", help="Filter to one folder, by name or UUID."
    ),
    output: str = OUTPUT_OPTION,
    json_out: bool = JSON_OPTION,
) -> None:
    """List automations in the configured env."""
    fmt = out.resolve_format(output, json_out)
    with cli_errors(LookupError):
        items = auto_tools.list_automations(folder=folder or None)

    def table() -> None:
        t = Table(title="Automations")
        t.add_column("api_name")
        t.add_column("name")
        t.add_column("type")
        t.add_column("active", justify="center")
        t.add_column("rev", justify="right")
        t.add_column("for", style="dim")
        t.add_column("folder", style="dim")
        for a in items:
            t.add_row(
                a["api_name"] or "",
                a["name"] or "",
                a["type"] or "",
                "✓" if a["active"] else "·",
                str(a["revision"]) if a["revision"] is not None else "",
                a["custom_object_name"] or "",
                a["folder_name"] or "",
            )
        console.print(t)

    out.render(
        fmt,
        json_data=items,
        table=table,
        csv_rows=items,
        csv_columns=[
            out.Column("api_name", "api_name"),
            out.Column("name", "name"),
            out.Column("type", "type"),
            out.Column("active", "active"),
            out.Column("revision", "revision"),
            out.Column("custom_object_name", "custom_object_name"),
            out.Column("folder_name", "folder_name"),
            out.Column("folder_id", "folder_id"),
        ],
    )


@autos_app.command("get")
def autos_get(
    api_name: str = typer.Argument(..., help="Automation api_name."),
    output: str = OUTPUT_OPTION,
    json_out: bool = typer.Option(
        False, "--json", help="Alias for --output json (summarised, no step configs)."
    ),
    raw_out: bool = typer.Option(
        False, "--raw", help="Emit full Kizen API response as JSON."
    ),
) -> None:
    """Show one automation in full (triggers + steps).

    `--output json` / `--json` emit the summary (no step configs);
    `--raw` emits the full API response; `--output csv` emits the step
    list (one row per step).
    """
    fmt = out.resolve_format(output, json_out)
    with cli_errors(LookupError):
        result = auto_tools.get_automation(api_name)

    if raw_out:
        typer.echo(json.dumps(result["raw"], indent=2))
        return

    def table() -> None:
        console.print(
            f"[bold]{result['name']}[/bold]  "
            f"[dim]({result['api_name']}, id={result['id']}, rev={result['revision']})[/dim]"
        )

        trig_table = Table(title="Triggers")
        trig_table.add_column("type")
        trig_table.add_column("description")
        for t in result["triggers"]:
            trig_table.add_row(t["trigger_type"] or "", t["description"] or "")
        console.print(trig_table)

        step_table = Table(title="Steps")
        step_table.add_column("ord", justify="right")
        step_table.add_column("id", style="dim")
        step_table.add_column("type")
        step_table.add_column("description")
        step_table.add_column("parent", style="dim")
        step_table.add_column("branch")
        for s in result["steps"]:
            step_table.add_row(
                str(s["order"]) if s["order"] is not None else "",
                (s["id"] or "")[:8],
                s["step_type"] or "",
                s["description"] or "",
                (s["parent_step_id"] or "")[:8],
                s["parent_condition"] or "",
            )
        console.print(step_table)

    out.render(
        fmt,
        json_data={k: v for k, v in result.items() if k != "raw"},
        table=table,
        csv_rows=result["steps"],
        csv_columns=[
            out.Column("order", "order"),
            out.Column("step_type", "step_type"),
            out.Column("description", "description"),
            out.Column("parent_step_id", "parent_step_id"),
            out.Column("parent_condition", "parent_condition"),
        ],
    )


@autos_app.command("llm-models")
def autos_llm_models(
    output: str = OUTPUT_OPTION,
    json_out: bool = JSON_OPTION,
) -> None:
    """List this business's enabled LLM models for call_llm/file_content_extraction/
    audio_transcription/condition llm_decision steps, with each provider's
    business_plugin_app_id (the value `call_llm.business_plugin_app_id` needs
    for any non-`kizen/*` model_name — see automation.md).
    """
    fmt = out.resolve_format(output, json_out)
    with cli_errors():
        rows = auto_tools.list_llm_models()

    def table() -> None:
        t = Table(title="LLM models")
        t.add_column("provider")
        t.add_column("model_name")
        t.add_column("label")
        t.add_column("business_plugin_app_id")
        t.add_column("call", justify="center")
        t.add_column("decision", justify="center")
        t.add_column("extract", justify="center")
        t.add_column("transcribe", justify="center")
        t.add_column("deprecated", justify="center")
        for r in rows:
            t.add_row(
                r["provider_name"] or "",
                r["model_value"] or "",
                r["model_label"] or "",
                r["business_plugin_app_id"] or "[dim]—[/dim]",
                "✓" if r["supports_call"] else "·",
                "✓" if r["supports_decision"] else "·",
                "✓" if r["supports_extraction"] else "·",
                "✓" if r["supports_transcription"] else "·",
                "✓" if r["is_deprecated"] else "·",
            )
        console.print(t)

    out.render(
        fmt,
        json_data=rows,
        table=table,
        csv_rows=rows,
        csv_columns=[
            out.Column("provider_name", "provider"),
            out.Column("model_value", "model_name"),
            out.Column("model_label", "label"),
            out.Column("business_plugin_app_id", "business_plugin_app_id"),
            out.Column("supports_call", "call"),
            out.Column("supports_decision", "decision"),
            out.Column("supports_extraction", "extract"),
            out.Column("supports_transcription", "transcribe"),
            out.Column("is_deprecated", "deprecated"),
        ],
    )


@autos_app.command("roundtrip")
def autos_roundtrip(
    api_name: str = typer.Argument(..., help="Automation api_name."),
    execute: bool = typer.Option(
        False,
        "--execute",
        "-x",
        help="PUT the translated payload back (intended no-op) and diff the result.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit full result as JSON."),
    show_payload: bool = typer.Option(
        False, "--payload", help="Print the translated PUT payload."
    ),
) -> None:
    """Verify GET→PUT translation fidelity for one automation.

    Translates the live automation into a PUT payload and validates the
    step graph. With --execute, PUTs the payload unchanged, re-fetches, and
    reports semantic drift — an empty diff means the translator is faithful
    for every step/trigger type in this automation.
    """
    with cli_errors(LookupError, PlanError):
        result = auto_tools.roundtrip_automation(api_name, execute=execute)

    if json_out:
        typer.echo(json.dumps(result, indent=2))
    else:
        console.print(
            f"[bold]{result['api_name']}[/bold]  "
            f"[dim](rev {result['revision_before']}, "
            f"{result['n_triggers']} triggers, {result['n_steps']} steps)[/dim]"
        )
        if show_payload:
            typer.echo(json.dumps(result["payload"], indent=2))
        if result["validation_problems"]:
            console.print("[red]structural validation FAILED:[/red]")
            for p in result["validation_problems"]:
                console.print(f"  [red]-[/red] {p}")
        elif not result["executed"]:
            console.print(
                "[green]translated + validated[/green] — dry run only; "
                "re-run with --execute to prove the round-trip live"
            )
        else:
            drift = result.get("drift") or []
            console.print(
                f"[dim]PUT ok — revision {result['revision_before']} → "
                f"{result.get('revision_after')}[/dim]"
            )
            if drift:
                console.print(f"[red]FAIL[/red] — {len(drift)} drift(s):")
                for d in drift:
                    console.print(
                        f"  [yellow]{d['path']}[/yellow]: "
                        f"{d['before']!r} → {d['after']!r}"
                    )
            else:
                console.print("[green]PASS — zero semantic drift[/green]")

    if result["validation_problems"] or (
        result.get("executed") and result.get("drift")
    ):
        raise typer.Exit(code=1)


@autos_app.command(
    "diff",
    epilog="Spec shape (an AutomationDef: triggers + step graph): see `kizen docs show automation`",
)
def autos_diff(
    api_name: str = typer.Argument(..., help="Automation api_name."),
    spec_file: str = typer.Option(
        "",
        "--spec-file",
        help="Path to JSON AutomationDef. Default: read from stdin.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit full result as JSON."),
) -> None:
    """Show what `automations update` from this spec would change on the
    live automation — read-only, no write is made.

    Triggers/steps are matched by `id` first (regardless of `key`/order),
    position among the rest as a fallback for a spec with no `id`s at all.
    `key`/`parent_key`/`prefix` are excluded from the comparison — they're
    per-side synthetic naming (see `kizen docs show automation`), not
    automation content — but a genuine reparenting still shows, compared by
    matched identity rather than raw key. Each line is labelled with the
    first octet of the step/trigger's `id` so it can be matched to what's
    visible in the UI; it is unique within one automation. Under `--json`, an
    added or removed step/trigger also carries its full `id` in the leaf
    value.
    """
    spec_dict, _from_stdin = _read_spec(spec_file)
    spec_api_name = spec_dict.get("api_name")
    if spec_api_name and spec_api_name != api_name:
        err_console.print(
            f"[red]error:[/red] spec api_name '{spec_api_name}' does not match "
            f"'{api_name}' — diffing against the wrong automation. Pass the "
            "spec's own api_name, or fix --spec-file."
        )
        raise typer.Exit(code=2)
    try:
        with cli_errors(LookupError, PlanError):
            result = auto_planners.diff_automation(spec_dict)
    except ValidationError as e:
        for err in e.errors():
            loc = ".".join(str(p) for p in err.get("loc", ())) or "spec"
            msg = err.get("msg", "invalid value")
            err_console.print(f"[red]spec error:[/red] {loc}: {msg}")
        raise typer.Exit(code=1) from e

    if json_out:
        typer.echo(json.dumps(result, indent=2))
        return

    console.print(
        f"[bold]{result['api_name']}[/bold]  [dim](rev {result['revision']})[/dim]"
    )
    diff = result["diff"]
    if not diff:
        console.print("[green]no changes[/green] — update would be a no-op")
        return
    console.print(f"[yellow]{len(diff)} change(s):[/yellow]")
    for d in diff:
        console.print(
            f"  [yellow]{d['path']}[/yellow]: {d['before']!r} → {d['after']!r}"
        )


def _step_label(step: dict[str, Any]) -> str:
    desc = (step.get("description") or step.get("user_description") or "").strip()
    if len(desc) > 72:
        desc = desc[:69] + "…"
    label = f"[bold]{step['key']}[/bold]"
    goto = step.get("action_go_to_automation_step")
    if goto:
        target = goto.get("step_key") or goto.get("trigger_key") or "?"
        label += f" [cyan]→ {target}[/cyan]"
    if step.get("should_skip_execution"):
        label += " [yellow](skipped)[/yellow]"
    if desc:
        label += f"  [dim]{desc}[/dim]"
    return label


def _render_step_tree(payload: dict[str, Any]) -> None:
    from rich.tree import Tree

    tree = Tree(f"[bold]{payload['name']}[/bold]  [dim]({payload['api_name']})[/dim]")
    trig_node = tree.add(f"[dim]triggers ({len(payload['triggers'])})[/dim]")
    for t in payload["triggers"]:
        desc = (t.get("description") or "").strip()
        trig_node.add(f"{t['key']}" + (f"  [dim]{desc[:60]}[/dim]" if desc else ""))
    if payload.get("variables"):
        var_node = tree.add(f"[dim]variables ({len(payload['variables'])})[/dim]")
        for v in payload["variables"]:
            var_node.add(f"{v.get('name')}  [dim]{v.get('data_type')}[/dim]")

    def add_children(node: Any, parent_key: str | None) -> None:
        for child in step_tools.children_of(payload, parent_key, branch=""):
            child_node = node.add(_step_label(child))
            descend(child_node, child)

    def descend(node: Any, step: dict[str, Any]) -> None:
        for branch, style in (("yes", "green"), ("no", "red")):
            kids = step_tools.children_of(payload, step["key"], branch=branch)
            if kids:
                branch_node = node.add(f"[{style}]{branch}[/{style}]")
                for child in kids:
                    descend(branch_node.add(_step_label(child)), child)
        add_children(node, step["key"])

    # The leading initialize_variable chain is always linear (the server
    # requires init-vars at the front), so render it flat instead of as a
    # one-step-deeper staircase per variable.
    frontier = step_tools.children_of(payload, None, branch="")
    while len(frontier) == 1 and frontier[0]["type"] == "initialize_variable":
        tree.add(_step_label(frontier[0]))
        frontier = step_tools.children_of(payload, frontier[0]["key"], branch="")
    for step in frontier:
        descend(tree.add(_step_label(step)), step)
    console.print(tree)


@autos_app.command("show")
def autos_show(
    api_name: str = typer.Argument(..., help="Automation api_name."),
    json_out: bool = typer.Option(
        False, "--json", help="Emit the translated wire payload as JSON."
    ),
) -> None:
    """Render the automation as a step tree with stable step keys.

    The keys shown (`s07_condition`) are the handles the `steps`
    subcommands take. They are synthesized deterministically from the live
    step order, so re-running `show` after any change gives the fresh set.
    """
    with cli_errors(LookupError, PlanError):
        result = auto_tools.show_automation(api_name)

    if json_out:
        typer.echo(json.dumps(result, indent=2))
        return
    console.print(
        f"[dim]rev {result['revision']}, "
        f"{'active' if result['active'] else 'inactive'}, "
        f"for {result['custom_object_name'] or 'global'}[/dim]"
    )
    _render_step_tree(result["payload"])


def _parse_start_variables(var: list[str], vars_json: str | None) -> dict[str, Any]:
    """Merge --vars-json ({name: value}) with repeatable --var name=value.

    --var wins on conflict. Returns an empty dict when neither is given.
    """
    variables: dict[str, Any] = {}
    if vars_json:
        try:
            parsed = json.loads(vars_json)
        except json.JSONDecodeError as e:
            raise typer.BadParameter(f"--vars-json is not valid JSON: {e}") from e
        if not isinstance(parsed, dict):
            raise typer.BadParameter(
                "--vars-json must be a JSON object mapping variable name → value."
            )
        variables.update(parsed)
    for item in var:
        name, sep, value = item.partition("=")
        if not sep or not name:
            raise typer.BadParameter(f"--var must be name=value (got {item!r}).")
        variables[name] = value
    return variables


@autos_app.command("start")
def autos_start(
    api_name: str = typer.Argument(..., help="Automation api_name."),
    record_id: str = typer.Option(
        None,
        "--record",
        "-r",
        help="Record/contact UUID to run on. Omit for global (record-less) automations.",
    ),
    var: list[str] = typer.Option(
        [],
        "--var",
        help="Seed a variable for this run: --var name=value (repeatable). "
        "Value is sent as a string; the server coerces it by the variable's type.",
    ),
    vars_json: str | None = typer.Option(
        None,
        "--vars-json",
        help="Seed variables from a JSON object, e.g. '{\"org_match\": true}'. "
        "Merged with --var (--var wins on conflict).",
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Trigger an automation, optionally on a record and seeding variables.

    Must use the automation api_name (not UUID) — the endpoint returns
    execution: null when a UUID is passed instead. `--var` / `--vars-json`
    override the automation's variable values for this run (validated against
    the automation's declared variables), which is the way to exercise it with
    a known input. The `--record` id is routed to the API's client_id for
    contact automations and record_id otherwise; it is optional for global
    (record-less) automations and required for record-based ones.

    Deliberately confirm-free: this is a runtime action (fire an existing
    automation on a record), not a schema mutation, so it sits outside the
    plan/preview/confirm gate that guards create/update. That is a standing
    decision, not an oversight.
    """
    variables = _parse_start_variables(var, vars_json)
    with cli_errors(LookupError):
        result = auto_tools.start_automation(
            api_name, record_id, variables=variables or None
        )

    if json_out:
        typer.echo(json.dumps(result, indent=2))
        return

    exec_id = result.get("execution_id")
    overrides = result.get("variable_overrides") or []
    if exec_id:
        console.print(f"[green]started[/green]  execution_id={exec_id}")
        entity = result.get("client_id") or result.get("record_id")
        if entity:
            target = "client_id" if result.get("client_id") else "record_id"
            console.print(f"[dim]on:[/dim] {target}={entity}")
        else:
            console.print("[dim]on:[/dim] (global — no record)")
        if overrides:
            seeded = ", ".join(f"{o['variable_name']}={o['value']}" for o in overrides)
            console.print(f"[dim]seeded:[/dim] {seeded}")
        console.print(f"[dim]View it with:[/dim] kizen automations runs view {exec_id}")
    else:
        console.print("[yellow]started — no execution ID in response[/yellow]")
        console.print(json.dumps(result.get("raw"), indent=2))


# ---------------------------------------------------------------------------
# automation diagnostics — modification history / failure history
# ---------------------------------------------------------------------------


@autos_app.command("modification-history")
def autos_modification_history(
    api_name: str = typer.Argument(..., help="Automation api_name."),
    date_from: str = typer.Option("", "--from", help="ISO datetime lower bound."),
    date_to: str = typer.Option("", "--to", help="ISO datetime upper bound."),
    event_type: list[str] = typer.Option(
        [], "--event-type", help="Filter by event type (repeatable)."
    ),
    search: str = typer.Option("", "--search", help="Free-text search."),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Who changed this automation, when, and what changed."""
    with cli_errors(LookupError):
        results = auto_tools.get_modification_history(
            api_name,
            date_from=date_from or None,
            date_to=date_to or None,
            event_type=event_type or None,
            search=search or None,
        )
    if json_out:
        typer.echo(json.dumps(results, indent=2, default=str))
        return
    table = Table(title=f"Modification history — {api_name}")
    table.add_column("when")
    table.add_column("event")
    table.add_column("by")
    for r in results:
        initiator = r.get("initiator") or {}
        by = initiator.get("email") or " ".join(
            filter(None, (initiator.get("first_name"), initiator.get("last_name")))
        )
        table.add_row(
            r.get("created", ""),
            r.get("type_display_name") or r.get("type_name", ""),
            by,
        )
    console.print(table)
    if not results:
        console.print("[dim]no modification history[/dim]")


@autos_app.command("failures")
def autos_failures(
    api_name: str = typer.Argument(..., help="Automation api_name."),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Recent step-failure history for an automation."""
    with cli_errors(LookupError):
        results = auto_tools.get_failures_history(api_name)
    if json_out:
        typer.echo(json.dumps(results, indent=2, default=str))
        return
    if not results:
        console.print("[dim]no recorded failures[/dim]")
        return
    typer.echo(json.dumps(results, indent=2, default=str))
