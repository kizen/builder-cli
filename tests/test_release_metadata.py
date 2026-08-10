"""Guards on the three files that have to agree about the version number.

`pyproject.toml` is the source of truth. Two other files copy it, and both
copies fail in ways that are annoying to diagnose from the symptom:

* `CHANGELOG.md` — a bump with no changelog section ships a release whose
  notes are empty, and `release.yml` builds its GitHub Release body from that
  section.
* `uv.lock` — the lockfile records the project's own version, so a bump
  without a re-lock makes CI's `uv sync --locked` fail with a resolution
  message that says nothing about the real cause.

These run in the source checkout (like the packaging guards); nothing here
ships in the wheel.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
LOCKFILE = REPO_ROOT / "uv.lock"


def _declared_version() -> str:
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)["project"]["version"]


def test_version_is_plain_semver():
    """No dev/local segments — `kizen --version` has to be sayable out loud."""
    version = _declared_version()
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), (
        f"version {version!r} is not a plain MAJOR.MINOR.PATCH; "
        "this project deliberately doesn't use scm-derived versions"
    )


def test_changelog_has_a_section_for_the_declared_version():
    text = CHANGELOG.read_text()
    version = _declared_version()
    assert re.search(rf"^## \[{re.escape(version)}\]", text, re.MULTILINE), (
        f"pyproject declares {version} but CHANGELOG.md has no `## [{version}]` "
        "section — write the entries in the change that makes them, then bump"
    )


def test_lockfile_agrees_with_pyproject():
    with LOCKFILE.open("rb") as fh:
        packages = tomllib.load(fh)["package"]
    locked = next(p for p in packages if p["name"] == "kizen-builder")
    assert locked["version"] == _declared_version(), (
        "uv.lock records a different project version than pyproject.toml — "
        "run `uv lock` after bumping, or CI's `uv sync --locked` will fail"
    )
