"""Guards that the docs tree actually ships inside the wheel.

This is the regression net for the class of bug that made the CLI
checkout-only: the docs lived outside the package, nothing declared them as
package data, and every failure was silent — `kizen init` "succeeded" and left
an environment folder with no operating instructions.

Tier 1 (this module, always on) proves the *declaration* is right by expanding
the `package-data` globs against the source tree — no build required, so it
runs in milliseconds on every commit. Tier 2 (`test_wheel_contents`) builds a
real wheel and inspects it, skipping if `build` isn't installed.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

from kizen_builder import docs

REPO_ROOT = Path(__file__).resolve().parents[1]
PKG_ROOT = Path(docs.__file__).resolve().parent
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _package_data_globs() -> list[str]:
    with PYPROJECT.open("rb") as fh:
        data = tomllib.load(fh)
    globs = data["tool"]["setuptools"]["package-data"]["kizen_builder"]
    assert globs, "kizen_builder package-data is empty"
    return list(globs)


def test_every_package_data_glob_matches_something():
    """A glob matching nothing is dead weight that hides a real gap.

    This is exactly how `schema/*.json` survived: it pointed at a directory
    that never existed, so the wheel shipped no data files at all.
    """
    dead = [g for g in _package_data_globs() if not list(PKG_ROOT.glob(g))]
    assert not dead, f"package-data globs match no files: {dead}"


def test_every_shipped_doc_is_covered_by_a_glob():
    """Adding a doc without extending the globs must fail here, not in the wild."""
    matched: set[Path] = set()
    for glob in _package_data_globs():
        matched.update(PKG_ROOT.glob(glob))

    on_disk = set((PKG_ROOT / "docs").rglob("*.md"))
    missed = sorted(p.relative_to(PKG_ROOT).as_posix() for p in on_disk - matched)
    assert not missed, (
        "these docs exist but no package-data glob ships them "
        f"(add one in pyproject.toml): {missed}"
    )


def test_docs_root_holds_the_expected_tree():
    root = docs.docs_root()
    assert root.is_dir()
    for guide in docs.GUIDE_TOPICS:
        assert (root / f"{guide}.md").is_file(), f"missing guide: {guide}"
    assert docs.specs_index().is_file()
    assert list(docs.specs_dir().glob("*.md"))


def test_every_listed_topic_resolves():
    """`docs list` must never advertise a topic `docs show` can't serve."""
    for topic in docs.list_topics():
        assert docs.topic_path(topic).is_file()


def test_unknown_topic_names_the_alternatives():
    with pytest.raises(LookupError) as exc:
        docs.topic_path("does-not-exist")
    # The error is a user's main discovery path; it must list what *is* there.
    assert "automation" in str(exc.value)


def test_docs_are_inside_the_package_not_the_repo_root():
    """The whole point: resolution must not depend on a checkout being present."""
    assert docs.docs_root() == PKG_ROOT / "docs"
    assert not (REPO_ROOT / ".kizen" / "specs").exists()
    assert not (REPO_ROOT / ".kizen" / "reference.md").exists()


# --- Tier 2: build a real wheel and look inside it --------------------------


@pytest.mark.wheel
def test_wheel_contents(tmp_path):
    """Build a wheel and assert the docs and entry point are really in it."""
    pytest.importorskip("build", reason="needs the `build` package (dev extra)")

    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(tmp_path)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    wheels = list(tmp_path.glob("*.whl"))
    assert len(wheels) == 1, f"expected one wheel, got {wheels}"

    with zipfile.ZipFile(wheels[0]) as zf:
        names = set(zf.namelist())
        entry_points = next(
            zf.read(n).decode() for n in names if n.endswith("entry_points.txt")
        )

    for guide in docs.GUIDE_TOPICS:
        assert f"kizen_builder/docs/{guide}.md" in names, f"wheel is missing {guide}.md"

    shipped_specs = {n for n in names if n.startswith("kizen_builder/docs/specs/")}
    on_disk_specs = set(docs.specs_dir().glob("*.md"))
    assert len(shipped_specs) == len(on_disk_specs), (
        f"wheel has {len(shipped_specs)} spec files, source tree has "
        f"{len(on_disk_specs)}"
    )

    assert "kizen = kizen_builder.cli:app" in entry_points
