"""`kizen messages` — email templates plus the automation-scoped messages that
`notify_member_via_email` steps reference. A separate surface, not nested
under `automations`, since templates aren't automation-specific.
"""

from __future__ import annotations

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
)
from kizen_builder.tools import messages as message_tools
from kizen_builder.tools.planners import messages as message_planners

messages_app = typer.Typer(
    help=(
        "Email templates and automation-scoped messages — the content "
        "notify_member_via_email steps reference (see `kizen docs show email-templates`). "
        "Kizen's builder UI 'select email' picker only recognizes a message "
        "as selected when it's seeded from a real template; that's what "
        "`create` does."
    ),
    no_args_is_help=True,
)
app.add_typer(messages_app, name="messages")

messages_templates_app = typer.Typer(help="Email templates.", no_args_is_help=True)
messages_app.add_typer(messages_templates_app, name="templates")


@messages_templates_app.command("list")
def messages_templates_list(
    output: str = OUTPUT_OPTION,
    json_out: bool = JSON_OPTION,
) -> None:
    """List email templates (pass one's name or UUID as `--template`)."""
    fmt = out.resolve_format(output, json_out)
    with cli_errors():
        templates = message_tools.list_templates()

    def table() -> None:
        t = Table(title="Email templates")
        t.add_column("id", style="dim")
        t.add_column("name")
        t.add_column("subject")
        for tmpl in templates:
            t.add_row(
                tmpl.get("id") or "", tmpl.get("name") or "", tmpl.get("subject") or ""
            )
        console.print(t)

    out.render(fmt, json_data=templates, table=table)


@messages_app.command("create")
def messages_create(
    api_name: str = typer.Argument(..., help="Automation api_name."),
    template: str = typer.Option(
        ...,
        "--template",
        help="Email template name or UUID (see `messages templates list`).",
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
    """Create an automation-scoped message from an email template.

    Reference the resulting UUID as the `email_template_id` (or `id`) in a
    notify_member_via_email step spec passed to `automations steps
    add`/`edit`. A message created any other way (raw content, no
    template behind it) won't show as selected in Kizen's builder UI even
    though the step technically references it.
    """
    _run_mutation(
        lambda: message_planners.plan_create_automation_message(api_name, template),
        dry_run=dry_run,
        yes=yes,
        json_out=json_out,
    )
