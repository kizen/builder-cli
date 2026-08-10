"""Live round-trip for the filter DSL: build → resolve → search → assert.

Every other file in this directory checks *shape* — a payload sent, a shape
read back. Filters are different: the DSL's whole job is producing a wire
query that Kizen's search endpoint interprets a specific way, and the only way
to prove that is to create real records, run a real filter through the real
search endpoint, and check that exactly the right records come back.

This file creates a handful of throwaway records on the shared session-scoped
``drift_object`` (a `conftest.py` fixture, auto-visible here), reusing the
"Drift Risk Level" dropdown field that sibling file's own
field round-trip creates when the whole suite runs, and adding a plain text
field and a checkbox field of its own if the object doesn't already have ones
usable for this file's cases. Everything created is registered with ``scratch``
immediately, same as everywhere else in this directory.

The last test exercises the filter-*group* (saved view) surface: create one
via the DSL, read it back, and confirm the read-back ``config`` is exactly
what ``docs/filters.md`` claims — already wire-shaped, safe to reuse raw
without going back through the DSL.
"""

from __future__ import annotations

from typing import Any

import pytest

from kizen_builder.api import custom_objects as co_api
from kizen_builder.api import records as records_api
from kizen_builder.api import saved_views as sv_api
from kizen_builder.api.saved_views import FILTER_GROUPS_BASE
from kizen_builder.api.schema import SchemaClient
from kizen_builder.filtering import All, Field, as_search_body, filter_context
from kizen_builder.tools.objects import get_object as get_object_tool
from kizen_builder.tools.planners.fields import plan_create_field
from kizen_builder.tools.planners.records import plan_create_records
from kizen_builder.tools.planners.saved_views import (
    _render_filter_config,
    plan_create_filter_group,
    plan_update_filter_group,
)
from tests.drift.conftest import debris_api_name, debris_name

pytestmark = pytest.mark.drift


# ---------------------------------------------------------------------------
# Fixtures: schema client bound to the drift env, and the fields/records this
# file's tests need on `drift_object`.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def schema_client(drift_client) -> SchemaClient:
    """Filter-DSL field/option lookups, bound explicitly to the drift client
    (never the module's own .env-backed default)."""
    return SchemaClient(drift_client)


def _ensure_field(
    drift_client,
    scratch,
    drift_object: dict[str, Any],
    display_name: str,
    field_type: str,
    options: list[str] | None = None,
) -> str:
    """Create a field on drift_object and return its server-derived api_name.

    Always creates — callers check for an existing usable field first and
    only fall back to this when none exists.
    """
    category = drift_object["categories"][0]["name"]
    spec: dict[str, Any] = {
        "name": display_name,
        "api_name": debris_api_name(field_type),
        "field_type": field_type,
    }
    if options is not None:
        spec["options"] = options
    plan = plan_create_field(drift_object["api_name"], spec, category=category)
    payload = plan.operations[0].payload
    created = co_api.create_field(drift_client, drift_object["uuid"], payload)
    scratch.track(
        "field",
        created["id"],
        lambda: co_api.delete_field(drift_client, drift_object["uuid"], created["id"]),
    )
    return created["name"]


@pytest.fixture(scope="session")
def text_field_api_name(drift_client, scratch, drift_object) -> str:
    """A plain `text` field to filter on. Every standard custom object has a
    default `name` field of this type; fall back to creating one only if that
    assumption ever stops holding."""
    obj = get_object_tool(drift_object["api_name"])
    existing = next(
        (
            f
            for f in obj["fields"]
            if not f.get("deleted")
            and (f["api_name"] == "name" or f["field_type"] == "text")
        ),
        None,
    )
    if existing is not None:
        return existing["api_name"]
    return _ensure_field(
        drift_client, scratch, drift_object, "Drift Filter Text", "text"
    )


@pytest.fixture(scope="session")
def risk_field_api_name(drift_client, scratch, drift_object) -> str:
    """The "Drift Risk Level" dropdown (Low/High) that
    ``test_dropdown_field_option_roundtrip`` in test_roundtrip_drift.py
    creates when the whole suite runs. Created here instead if this file runs
    on its own (e.g. `pytest -m drift -k filtering`), so this test file is
    self-contained either way."""
    obj = get_object_tool(drift_object["api_name"])
    existing = next(
        (
            f
            for f in obj["fields"]
            if not f.get("deleted") and f.get("display_name") == "Drift Risk Level"
        ),
        None,
    )
    if existing is not None:
        return existing["api_name"]
    return _ensure_field(
        drift_client,
        scratch,
        drift_object,
        "Drift Risk Level",
        "dropdown",
        options=["Low", "High"],
    )


@pytest.fixture(scope="session")
def checkbox_field_api_name(drift_client, scratch, drift_object) -> str:
    """A throwaway checkbox field — drift_object has no default one."""
    return _ensure_field(
        drift_client, scratch, drift_object, "Drift Flagged", "checkbox"
    )


@pytest.fixture(scope="session")
def filter_records(
    drift_client,
    scratch,
    drift_object,
    text_field_api_name,
    risk_field_api_name,
    checkbox_field_api_name,
) -> dict[str, str]:
    """Four throwaway records covering every case the tests below check.

    | label        | text has "Widget"/"Gadget" | risk    | checkbox |
    |--------------|------------------------------|---------|----------|
    | widget_low   | Widget                       | Low     | checked  |
    | widget_high  | Widget                       | High    | unchecked|
    | gadget_blank | Gadget                       | (blank) | checked  |
    | gadget_high  | Gadget                       | High    | unchecked|
    """
    row_specs: dict[str, dict[str, Any]] = {
        "widget_low": {"token": "Widget", "risk": "Low", "checkbox": True},
        "widget_high": {"token": "Widget", "risk": "High", "checkbox": False},
        "gadget_blank": {"token": "Gadget", "risk": None, "checkbox": True},
        "gadget_high": {"token": "Gadget", "risk": "High", "checkbox": False},
    }
    records_input: list[dict[str, Any]] = []
    for label, spec in row_specs.items():
        row: dict[str, Any] = {
            text_field_api_name: debris_name(f"record {spec['token']} {label}"),
            checkbox_field_api_name: spec["checkbox"],
        }
        if spec["risk"] is not None:
            row[risk_field_api_name] = spec["risk"]
        records_input.append(row)

    plan = plan_create_records(drift_object["api_name"], records_input)
    ids: dict[str, str] = {}
    for label, op in zip(row_specs, plan.operations, strict=True):
        created = records_api.create_record(
            drift_client, drift_object["uuid"], op.payload["fields"]
        )
        scratch.track(
            "record",
            created["id"],
            lambda rid=created["id"]: records_api.delete_record(
                drift_client, drift_object["uuid"], rid
            ),
        )
        ids[label] = created["id"]
    return ids


def _search(drift_client, drift_object, query: list[dict[str, Any]]) -> set[str]:
    results = records_api.search_records(
        drift_client, drift_object["uuid"], filters=query
    )
    return {r["id"] for r in results}


# ---------------------------------------------------------------------------
# 1. Text field `contains`
# ---------------------------------------------------------------------------


def test_text_contains_filter(
    drift_client, drift_object, schema_client, text_field_api_name, filter_records
):
    with filter_context(drift_object["uuid"], client=schema_client):
        query = as_search_body(All(Field(text_field_api_name).contains("Widget")))[
            "query"
        ]

    assert _search(drift_client, drift_object, query) == {
        filter_records["widget_low"],
        filter_records["widget_high"],
    }


# ---------------------------------------------------------------------------
# 2. Dropdown `is_any_of`
# ---------------------------------------------------------------------------


def test_dropdown_is_any_of_filter(
    drift_client, drift_object, schema_client, risk_field_api_name, filter_records
):
    with filter_context(drift_object["uuid"], client=schema_client):
        query = as_search_body(All(Field(risk_field_api_name).is_any_of("High")))[
            "query"
        ]

    assert _search(drift_client, drift_object, query) == {
        filter_records["widget_high"],
        filter_records["gadget_high"],
    }


# ---------------------------------------------------------------------------
# 3. `is_blank` — one token, distinguished by its boolean value
# ---------------------------------------------------------------------------


def test_is_blank_filter(
    drift_client, drift_object, schema_client, risk_field_api_name, filter_records
):
    with filter_context(drift_object["uuid"], client=schema_client):
        blank_query = as_search_body(All(Field(risk_field_api_name).is_blank()))[
            "query"
        ]
        not_blank_query = as_search_body(All(Field(risk_field_api_name).not_blank()))[
            "query"
        ]

    assert _search(drift_client, drift_object, blank_query) == {
        filter_records["gadget_blank"]
    }
    assert _search(drift_client, drift_object, not_blank_query) == {
        filter_records["widget_low"],
        filter_records["widget_high"],
        filter_records["gadget_high"],
    }


# ---------------------------------------------------------------------------
# 4. Checkbox `is_checked` / `not_checked`
# ---------------------------------------------------------------------------


def test_checkbox_filter(
    drift_client, drift_object, schema_client, checkbox_field_api_name, filter_records
):
    with filter_context(drift_object["uuid"], client=schema_client):
        checked_query = as_search_body(
            All(Field(checkbox_field_api_name).is_checked())
        )["query"]
        unchecked_query = as_search_body(
            All(Field(checkbox_field_api_name).not_checked())
        )["query"]

    assert _search(drift_client, drift_object, checked_query) == {
        filter_records["widget_low"],
        filter_records["gadget_blank"],
    }
    assert _search(drift_client, drift_object, unchecked_query) == {
        filter_records["widget_high"],
        filter_records["gadget_high"],
    }


# ---------------------------------------------------------------------------
# 5. Filter group round trip: a read-back `config` is already wire-shaped.
# ---------------------------------------------------------------------------


def test_filter_group_readback_is_wire_shaped_passthrough(
    drift_client, scratch, drift_object, risk_field_api_name, filter_records
):
    name = debris_name("filter group high risk")
    plan = plan_create_filter_group(
        drift_object["api_name"],
        {
            "name": name,
            "config": {
                "all": [
                    {"field": risk_field_api_name, "op": "is_any_of", "value": ["High"]}
                ]
            },
        },
    )
    payload = plan.operations[0].payload
    created = sv_api.create_saved_view(
        drift_client, drift_object["uuid"], FILTER_GROUPS_BASE, payload
    )
    scratch.track(
        "filter group",
        created["id"],
        lambda: sv_api.delete_saved_view(
            drift_client, drift_object["uuid"], FILTER_GROUPS_BASE, created["id"]
        ),
    )

    live = sv_api.get_saved_view(
        drift_client, drift_object["uuid"], FILTER_GROUPS_BASE, created["id"]
    )
    config = live["config"]
    assert set(config) == {"and", "query", "invalid"}
    assert config["query"], "expected at least one query group in the read-back config"

    # Behavioral: the read-back config is directly usable as a raw records
    # search filter, with no DSL re-resolution — the same clause that built the
    # filter group also selects the right records straight from the read-back.
    assert _search(drift_client, drift_object, config["query"]) == {
        filter_records["widget_high"],
        filter_records["gadget_high"],
    }

    # Structural: filters.md claims a filter read back from Kizen is *already*
    # wire-shaped and should be reused as a raw passthrough, not re-run through
    # the DSL. `_render_filter_config` is the function every saved-view write
    # funnels through — feeding it the read-back config must be a no-op.
    rendered = _render_filter_config(config, drift_object["api_name"])
    assert rendered == config

    # And the update planner — which diffs a proposed new config against the
    # live one — must see "no changes" when handed exactly what it just read
    # back, i.e. the update is "accepted without modification".
    update_plan = plan_update_filter_group(
        drift_object["api_name"], created["id"], {"config": config}
    )
    assert update_plan.operations[0].action == "skip"
