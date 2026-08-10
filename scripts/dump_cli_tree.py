"""Dump the full kizen command tree + every command's --help to stdout.

Used to prove the task-5 cli.py split changed nothing a user can see: capture
before, capture after, diff. A silently-dropped `add_typer` is the failure mode
there, and no existing test would catch it.

Walks the Typer app tree directly rather than shelling out per command, so it
stays fast and can't miss a sub-app that isn't reachable by guessing names.

Two things this deliberately does NOT do:

- import `click`. typer 0.27 dropped that dependency and vendors it as
  `typer._click`, so a freshly-synced venv for this project has no top-level
  click at all. A harness reaching for `click.testing` works only on a machine
  with a stale leftover click and fails everywhere else.
- go through `typer.testing.CliRunner`. Its `invoke` expects a `Typer` app and
  converts it internally, so it can't be handed the already-converted
  sub-command objects that walking the tree produces.

Rendering help off each command's own `get_help` is what's left, and it's also
the closest thing to what a user sees.

Usage:  uv run python dump_cli_tree.py > before.txt
"""

from __future__ import annotations

import os
import sys

# Fixed width and no color, so the captured text depends on the CLI and not on
# whoever's terminal ran it. Must be set before typer's rich console is built.
os.environ["COLUMNS"] = "100"
os.environ["TERM"] = "dumb"
os.environ["NO_COLOR"] = "1"

from typer._click.core import Context  # noqa: E402
from typer.main import get_command  # noqa: E402

from kizen_builder.cli import app  # noqa: E402


def walk(cmd, path: list[str], out: list[str]) -> None:
    name = " ".join(path)
    out.append(f"===== {name or 'kizen'} =====")
    out.append(cmd.get_help(Context(cmd, info_name=name or "kizen")).rstrip())
    out.append("")

    # Groups expose `.commands`; leaf commands don't. Sorted so the dump order
    # is stable rather than registration-order-dependent.
    sub = getattr(cmd, "commands", None)
    if sub:
        for key in sorted(sub):
            walk(sub[key], [*path, key], out)


def main() -> int:
    out: list[str] = []
    walk(get_command(app), [], out)
    sys.stdout.write("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
