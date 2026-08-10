"""`kizen init` — store credentials centrally and pin this directory to the
profile.
"""

from __future__ import annotations

import re
from pathlib import Path

import typer
from rich.prompt import Prompt

from kizen_builder import docs as docs_res
from kizen_builder import profiles
from kizen_builder.api.client import KizenAPIError, KizenClient
from kizen_builder.cli._shared import app, console, err_console
from kizen_builder.config import EnvConfig


def _validate_creds(cfg: EnvConfig) -> None:
    """Confirm credentials work with a cheap live read before we store them."""
    with KizenClient(cfg) as client:
        client.get("/api/custom-objects", params={"page_size": 1})


def _default_profile_name(directory: Path) -> str:
    """A sane profile default from the folder name: 'Builder - Acme' -> 'acme'."""
    name = re.sub(r"[^a-z0-9]+", "-", directory.name.lower()).strip("-")
    # Folders are commonly named "Builder - <env>"; the prefix isn't the env.
    name = re.sub(r"^builder-", "", name)
    return name or "default"


def _ask(label: str, default: str, *, flag: str, password: bool = False) -> str:
    """Ask for a value, falling back to the default when there's no input.

    Handles all three ways `kizen init` gets driven: an interactive terminal,
    piped answers (both read normally), and a fully non-interactive run with
    nothing on stdin — which would otherwise abort on the first prompt even
    when every value was supplied by flag or has a usable default. A missing
    value with no default is a clean usage error naming the flag to pass,
    rather than an EOF traceback.
    """
    try:
        return Prompt.ask(label, default=default, password=password)
    except EOFError:
        if default:
            return default
        err_console.print(
            f"[red]error:[/red] {label} is required and there's nothing on stdin. "
            f"Pass {flag} (or set the matching KIZEN_* environment variable)."
        )
        raise typer.Exit(code=2) from None


@app.command()
def init(
    profile: str = typer.Option(
        None,
        "--profile",
        "-p",
        "--env",
        "-e",
        help="Profile name for this env (e.g. acme-sandbox). Prompts if omitted.",
    ),
    api_key_opt: str = typer.Option(
        None, "--api-key", envvar="KIZEN_API_KEY", help="API key (else prompts)."
    ),
    business_id_opt: str = typer.Option(
        None,
        "--business-id",
        envvar="KIZEN_BUSINESS_ID",
        help="Business id (else prompts).",
    ),
    user_id_opt: str = typer.Option(
        None, "--user-id", envvar="KIZEN_USER_ID", help="User id (else prompts)."
    ),
    base_url: str = typer.Option(profiles.DEFAULT_BASE_URL, help="Kizen base URL."),
    no_pin: bool = typer.Option(
        False, "--no-pin", help="Store credentials only; don't pin this directory."
    ),
    skip_validation: bool = typer.Option(
        False, "--skip-validation", help="Don't verify credentials with a live call."
    ),
    refresh_stubs: bool = typer.Option(
        False,
        "--refresh-stubs",
        help=(
            "Overwrite existing CLAUDE.md / AGENTS.md with the current stub. "
            "Discards anything you added to them."
        ),
    ),
) -> None:
    """Set up this directory as a Kizen environment folder.

    Stores credentials centrally (`~/.config/kizen/credentials.toml`, 0600),
    pins this directory to the profile via `.kizen/profile` so every command
    run here targets it — refusing any env with a different business_id — and
    writes the agent-instruction stubs.

    Every value can be supplied as a flag or a `KIZEN_*` environment variable;
    anything still missing is prompted for, so this works interactively and
    headlessly from the same command.
    """
    cwd = Path.cwd()
    if not profile:
        profile = _ask("Profile name", _default_profile_name(cwd), flag="--profile")

    existing = profiles.get_profile(profile)

    api_key = api_key_opt or _ask(
        "API_KEY",
        existing.api_key if existing else "",
        flag="--api-key",
        password=True,
    )
    business_id = business_id_opt or _ask(
        "BUSINESS_ID",
        existing.business_id if existing else "",
        flag="--business-id",
    )
    user_id = user_id_opt or _ask(
        "USER_ID",
        existing.user_id if existing else "",
        flag="--user-id",
    )
    base_url_in = _ask(
        "BASE_URL",
        existing.base_url if existing else base_url,
        flag="--base-url",
    ).rstrip("/")

    creds = profiles.ProfileCreds(
        name=profile,
        api_key=api_key,
        business_id=business_id,
        user_id=user_id,
        base_url=base_url_in,
    )

    if not skip_validation:
        cfg = EnvConfig(
            name=profile.lower(),
            api_key=api_key,
            business_id=business_id,
            user_id=user_id,
            base_url=base_url_in,
        )
        try:
            _validate_creds(cfg)
        except KizenAPIError as exc:
            err_console.print(
                f"[red]Credential check failed[/red] ({exc.status_code}): {exc.message}\n"
                "Nothing was written. Re-run and re-enter the values, or pass "
                "--skip-validation to store them anyway."
            )
            raise typer.Exit(code=1) from exc
        console.print("[green]credentials verified[/green] against the live env")

    stored_at = profiles.write_profile(creds)
    console.print(f"[green]stored profile[/green] [bold]{profile}[/bold] → {stored_at}")

    if no_pin:
        console.print(
            "[dim]directory not pinned; set KIZEN_PROFILE or pass --profile "
            "to target this env.[/dim]"
        )
    else:
        pin_path = profiles.write_pin(profile, business_id, cwd)
        console.print(
            f"[green]pinned[/green] [bold]{cwd.name}[/bold] to "
            f"[bold]{profile}[/bold] (business_id {business_id}) → {pin_path}"
        )

    # Folder scaffolding is independent of the pin — a folder someone drives
    # with --profile still wants the instruction stubs.
    for dead in docs_res.clear_legacy_links(cwd):
        console.print(f"[yellow]removed stale link[/yellow] {dead.name}")

    for written in docs_res.write_stubs(cwd, profile, force=refresh_stubs):
        console.print(f"[green]wrote[/green] {written.name}")

    console.print(
        "\n[bold]Next:[/bold] open this folder in Claude Code and describe what "
        "you want to build.\n"
        "[dim]The agent reads CLAUDE.md, which points it at "
        "`kizen docs show operating`.[/dim]"
    )
