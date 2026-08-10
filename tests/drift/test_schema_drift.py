"""Half one of the drift check: has the published schema moved under us?

Fetches ``GET /api/docs/schema`` from the configured drift environment, reduces
it to the mutation contracts this CLI actually writes to (see
``tests/drift/contracts.py``), and diffs that against the committed snapshot.

What this half is good for: an endpoint or a request field **appearing or
disappearing**, going newly required, or changing type. What it cannot tell you
is whether a payload still *works* — the schema disagrees with live behavior in
several documented places. That is what ``test_roundtrip_drift.py`` is for.

To accept a legitimate upstream change:

    KIZEN_DRIFT_PROFILE=<name> KIZEN_DRIFT_UPDATE_SNAPSHOT=1 uv run pytest -m drift

then read `git diff tests/drift/schema_snapshot.json` before committing.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tests.drift.contracts import (
    KNOWN_UNDOCUMENTED_BLOCKS,
    SNAPSHOT_PATH,
    UPDATE_ENV_VAR,
    diff,
    extract,
    load_snapshot,
    save_snapshot,
    tracked,
)

pytestmark = pytest.mark.drift


def test_schema_endpoint_is_an_openapi_document(openapi_schema):
    """The premise of this whole half, asserted rather than assumed."""
    assert openapi_schema.get("openapi", "").startswith("3."), openapi_schema.get(
        "openapi"
    )
    assert openapi_schema["paths"], "schema returned no paths"
    assert openapi_schema.get("components", {}).get("schemas"), (
        "schema returned no components"
    )


def test_tracked_contracts_resolve_except_the_known_gaps(openapi_schema):
    """Every contract in scope must resolve, or be a documented gap.

    Reported before the field-level diff so a vanished endpoint names its
    surface instead of showing up as a wall of removed fields. Fails in both
    directions: newly missing, and newly *documented* (which means an entry in
    ``KNOWN_UNDOCUMENTED_BLOCKS`` is now a lie).
    """
    live = extract(openapi_schema)
    missing = {k for k, v in live.items() if not v.get("present")}

    unexpected = sorted(missing - set(KNOWN_UNDOCUMENTED_BLOCKS))
    if unexpected:
        pytest.fail(
            "Tracked contracts absent from the live schema:\n  "
            + "\n  ".join(unexpected)
            + "\n\nEither the endpoint moved (fix kizen_builder.api + the "
            "contract entry) or the schema stopped documenting it (record it in "
            "KNOWN_UNDOCUMENTED_BLOCKS with live evidence and rely on the "
            "round-trip half).",
            pytrace=False,
        )

    now_documented = sorted(set(KNOWN_UNDOCUMENTED_BLOCKS) - missing)
    if now_documented:
        pytest.fail(
            "The schema now documents contracts recorded as undocumented:\n  "
            + "\n  ".join(
                f"{k}\n      was: {KNOWN_UNDOCUMENTED_BLOCKS[k]}"
                for k in now_documented
            )
            + "\n\nDrop those KNOWN_UNDOCUMENTED_BLOCKS entries.",
            pytrace=False,
        )


def test_no_schema_drift(openapi_schema, drift_config, update_snapshot):
    live = extract(openapi_schema)

    if update_snapshot:
        save_snapshot(
            live,
            {
                "captured": datetime.now(UTC).strftime("%Y-%m-%d"),
                "openapi": openapi_schema.get("openapi"),
                "info": openapi_schema.get("info"),
                "base_url": drift_config.base_url,
                "contracts_tracked": len(tracked()),
                "how_to_refresh": (
                    f"KIZEN_DRIFT_PROFILE=<profile> {UPDATE_ENV_VAR}=1 "
                    "uv run pytest -m drift"
                ),
            },
        )
        pytest.skip(f"snapshot rewritten: {SNAPSHOT_PATH} — review the git diff")

    snapshot = load_snapshot()
    d = diff(snapshot["contracts"], live)
    if d:
        pytest.fail(
            "Kizen's published schema no longer matches the committed snapshot "
            f"(captured {snapshot['_meta'].get('captured')}).\n\n"
            + d.report()
            + "\n\nDecide which side is wrong. If the change is legitimate, "
            f"re-run with {UPDATE_ENV_VAR}=1 and review the diff before "
            "committing.",
            pytrace=False,
        )
