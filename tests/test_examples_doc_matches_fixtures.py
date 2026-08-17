"""The worked-example doc must never quietly diverge from its fixtures.

`examples.md` shows hand-authored JSON for the object, its fields, the
activity type, and the automation — the same JSON, by construction, that
`tests/drift/test_worked_examples.py` applies against a real environment.
Both halves read from the fixture files under
`tests/fixtures/examples/service_ticket/`; this test is what makes that a
guarantee rather than a convention. A fixture immediately preceded by an
`<!-- fixture: ... -->` marker comment must be byte-for-byte (modulo a
trailing newline) what the marker names on disk.

Runs in the default, every-commit suite — no live environment, no marker.
"""

from __future__ import annotations

import re
from pathlib import Path

from kizen_builder import docs

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_ROOT = REPO_ROOT / "tests" / "fixtures"

_MARKER_RE = re.compile(
    r"<!--\s*fixture:\s*(?P<path>[^\s]+?)\s*-->\n```(?:json)?\n(?P<body>.*?)\n```",
    re.DOTALL,
)


def _examples_doc_text() -> str:
    return docs.topic_path("examples").read_text()


def _marked_blocks() -> list[tuple[str, str]]:
    """Every ``(fixture relative path, fenced block body)`` pair in the doc."""
    return [
        (m.group("path"), m.group("body"))
        for m in _MARKER_RE.finditer(_examples_doc_text())
    ]


def test_the_doc_actually_has_marked_fixture_blocks():
    """A guard against the regex silently matching nothing after an edit."""
    blocks = _marked_blocks()
    assert len(blocks) >= 3, (
        "expected at least the object, fields, and automation blocks to carry "
        f"a '<!-- fixture: ... -->' marker; found {len(blocks)}"
    )


def test_every_marked_fixture_path_exists():
    for rel_path, _ in _marked_blocks():
        assert (FIXTURES_ROOT / rel_path).is_file(), (
            f"examples.md marks a fixture at '{rel_path}' that doesn't exist "
            f"under {FIXTURES_ROOT}"
        )


def test_marked_blocks_are_byte_identical_to_their_fixture():
    """The whole point: doc prose and the committed fixture never diverge."""
    mismatches = []
    for rel_path, body in _marked_blocks():
        on_disk = (FIXTURES_ROOT / rel_path).read_text()
        if body.strip("\n") != on_disk.strip("\n"):
            mismatches.append(rel_path)
    assert not mismatches, (
        "examples.md's fenced block no longer matches its fixture (or vice "
        f"versa) for: {mismatches}. Edit whichever one is stale, not both "
        "independently."
    )


def test_every_service_ticket_fixture_is_referenced():
    """Catches the opposite drift: a fixture nobody points at from the doc."""
    referenced = {rel_path for rel_path, _ in _marked_blocks()}
    on_disk = {
        f"examples/service_ticket/{p.name}"
        for p in (FIXTURES_ROOT / "examples" / "service_ticket").glob("*.json")
    }
    orphaned = on_disk - referenced
    assert not orphaned, (
        f"fixture(s) under tests/fixtures/examples/service_ticket/ that "
        f"examples.md never shows: {orphaned}"
    )
