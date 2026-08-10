"""Half two of the drift check: do the payloads still *work*?

The schema-diff half can only see what Kizen documents. This half creates real
entities in a disposable environment from the same payload builders the golden
offline tests assert as literals, reads them back, checks the shape the repo
believes, and deletes them.

Scope is deliberately small — the riskiest payloads only:

* **custom object** create/read (+ the ``pipeline``-required quirk the schema
  does not mark required)
* **field** create/read for the two most translation-heavy field types
  (``dropdown`` option pairs, ``wysiwyg`` -> ``longtext`` + markdown meta)
* **permission group** create/read — a ~35 KB body the schema declares one
  field of

Automations get a file of their own — ``test_roundtrip_automations.py`` — since
that surface needs coverage of every wired step and trigger type rather than
one representative payload. The cross-surface reconciliation at the bottom of
this file still reaches into it via the ``drift_automation`` fixture.

Everything created is registered for deletion the moment the POST returns; see
``Scratch`` in ``conftest.py`` for why that ordering matters.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.drift.conftest import DEBRIS_PREFIX, debris_api_name, debris_name
from tests.drift.contracts import KNOWN_SCHEMA_OMISSIONS, _follow, _ref_name

pytestmark = pytest.mark.drift


# ---------------------------------------------------------------------------
# Fixtures that create (and always destroy) live entities
# ---------------------------------------------------------------------------


# `drift_object`, `drift_related_object` and `drift_automation` live in
# `conftest.py` — they are shared with `test_roundtrip_automations.py`, and a
# fixture defined in a test module is invisible to every other module.


@pytest.fixture(scope="session")
def drift_pipeline_object(drift_client, scratch) -> dict[str, Any]:
    """A throwaway pipeline object — exercises the defaulted placeholder stage."""
    from kizen_builder.api import custom_objects as co_api
    from kizen_builder.models.spec import ObjectDef
    from kizen_builder.tools.planners.objects import _build_object_payload

    spec = ObjectDef(
        name=debris_name("pipeline"),
        api_name=debris_api_name("pipeline"),
        object_type="pipeline",
    )
    payload = _build_object_payload(spec)
    created = co_api.create_object(drift_client, payload)
    scratch.track(
        "pipeline object",
        created["id"],
        lambda: co_api.delete_object(drift_client, created["id"]),
    )
    return {
        "sent": payload,
        "live": co_api.get_object(drift_client, created["id"]),
        "uuid": created["id"],
    }


@pytest.fixture(scope="session")
def drift_permission_group(drift_client, scratch) -> dict[str, Any]:
    """A throwaway permission group built by the real default-shape builder."""
    from kizen_builder.api import permissions as perm_api
    from kizen_builder.tools.planners.permissions import plan_create_permission_group

    name = debris_name("permgroup")
    plan = plan_create_permission_group(name)
    payload = plan.operations[0].payload
    created = perm_api.create_permission_group(drift_client, payload)
    scratch.track(
        "permission group",
        created["id"],
        lambda: perm_api.delete_permission_group(drift_client, created["id"]),
    )
    return {
        "sent": payload,
        "live": perm_api.get_permission_group(drift_client, created["id"]),
        "uuid": created["id"],
        "name": name,
    }


# ---------------------------------------------------------------------------
# Objects
# ---------------------------------------------------------------------------


def test_object_create_roundtrip(drift_object):
    sent, live = drift_object["sent"], drift_object["live"]
    assert live["object_type"] == sent["object_type"]
    assert live["object_name"] == sent["object_name"]
    assert live["entity_name"] == sent["entity_name"]
    # The api_name we asked for is advisory: the server derives its own and
    # returns it as `name`. Several planners look objects up by that value, so a
    # change here would break resolution everywhere.
    assert live["name"], "server returned no derived api_name"
    assert live["is_custom"] is True
    # Every new object comes with exactly one default field category, which is
    # what `plan_create_field` resolves a category *name* against.
    assert len(drift_object["categories"]) == 1
    assert drift_object["categories"][0]["name"]


def test_pipeline_object_defaults_a_placeholder_stage(drift_pipeline_object):
    """The planner injects one 'Open' stage; confirm live keeps it."""
    stages = drift_pipeline_object["live"]["pipeline"]["stages"]
    assert [s["name"] for s in stages] == ["Open"]
    assert stages[0]["status"] == "open"
    assert stages[0]["order"] == 0
    assert stages[0]["id"], "server assigned no stage id"


def test_pipeline_is_required_live_but_not_in_the_schema(
    drift_client, openapi_schema, scratch
):
    """The reason a schema diff alone is not enough, asserted from both sides.

    ``CustomObjectRequest`` lists ``pipeline`` as an optional property; the live
    endpoint rejects a pipeline-type object without it. If this test starts
    failing because the POST *succeeds*, the planner's placeholder-stage
    workaround (`_build_pipeline_stages`) can go.
    """
    from kizen_builder.api import custom_objects as co_api
    from kizen_builder.api.client import KizenAPIError

    schemas = openapi_schema["components"]["schemas"]
    body_ref = openapi_schema["paths"]["/api/custom-objects"]["post"]["requestBody"][
        "content"
    ]["application/json"]["schema"]["$ref"]
    body = schemas[_ref_name(body_ref)]
    assert "pipeline" in body["properties"], "schema no longer declares `pipeline`"
    assert "pipeline" not in (body.get("required") or []), (
        "the schema now marks `pipeline` required, so this divergence is closed "
        "— drop this test and the note above KNOWN_SCHEMA_OMISSIONS in "
        "tests/drift/contracts.py"
    )

    name = debris_name("nopipeline")
    payload = {
        "object_name": name,
        "entity_name": name,
        "object_type": "pipeline",
        "default_on_activities": True,
    }
    try:
        created = co_api.create_object(drift_client, payload)
    except KizenAPIError as exc:
        assert exc.status_code == 400, f"expected 400, got {exc.status_code}: {exc}"
        assert "pipeline" in str(exc.body).lower(), exc.body
        return
    # Unexpected success: register the deleter before failing so it still goes.
    scratch.track(
        "unexpected pipeline object",
        created["id"],
        lambda: co_api.delete_object(drift_client, created["id"]),
    )
    pytest.fail(
        "a pipeline object was accepted with no `pipeline` block — live behavior "
        "now matches the schema. Drop the placeholder-stage workaround in "
        "kizen_builder.tools.planners.objects._build_pipeline_stages and the "
        "KNOWN_SCHEMA_OMISSIONS entry for POST /api/custom-objects."
    )


# ---------------------------------------------------------------------------
# Fields
# ---------------------------------------------------------------------------


def _create_field(drift_client, scratch, drift_object, spec: dict[str, Any]):
    from kizen_builder.api import custom_objects as co_api
    from kizen_builder.tools.planners.fields import plan_create_field

    category = drift_object["categories"][0]["name"]
    plan = plan_create_field(drift_object["api_name"], spec, category=category)
    payload = plan.operations[0].payload
    created = co_api.create_field(drift_client, drift_object["uuid"], payload)
    scratch.track(
        "field",
        created["id"],
        lambda: co_api.delete_field(drift_client, drift_object["uuid"], created["id"]),
    )
    return payload, created


def test_dropdown_field_option_roundtrip(drift_client, scratch, drift_object):
    """``{name, code}`` pairs go out; ``{id, code, name, order, meta}`` comes back."""
    payload, created = _create_field(
        drift_client,
        scratch,
        drift_object,
        {
            "name": "Drift Risk Level",
            "api_name": debris_api_name("dropdown"),
            "field_type": "dropdown",
            "options": ["Low", "High"],
        },
    )
    assert payload["options"] == [
        {"name": "Low", "code": "Low"},
        {"name": "High", "code": "High"},
    ]
    assert created["field_type"] == "dropdown"
    options = created["options"]
    assert [o["name"] for o in options] == ["Low", "High"]
    assert [o["code"] for o in options] == ["Low", "High"]
    assert all(o["id"] for o in options), "server assigned no option ids"
    # order is 1-based on read even though it is never sent
    assert [o["order"] for o in options] == [1, 2]


def test_wysiwyg_field_is_stored_as_longtext_with_markdown_meta(
    drift_client, scratch, drift_object
):
    """`wysiwyg` is a CLI-side alias: the wire type is longtext + markdown meta."""
    payload, created = _create_field(
        drift_client,
        scratch,
        drift_object,
        {
            "name": "Drift Care Summary",
            "api_name": debris_api_name("wysiwyg"),
            "field_type": "wysiwyg",
        },
    )
    assert payload["field_type"] == "longtext"
    assert payload["meta"] == {"is_markdown": True}
    assert created["field_type"] == "longtext"
    assert created["meta"].get("is_markdown") is True


# Automation round-trips — the `drift_automation` branching checks plus live
# coverage of every wired step and trigger type — live in
# `test_roundtrip_automations.py`.


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


def test_permission_group_create_roundtrip(drift_permission_group):
    sent, live = drift_permission_group["sent"], drift_permission_group["live"]
    assert live["name"] == drift_permission_group["name"]
    assert live["name"].startswith(DEBRIS_PREFIX)
    # Every section dict we sent must come back (the server normalizes values
    # to each section's allowed_access, so compare keys, not values).
    sent_sections = {k for k in sent if k.endswith("_section")}
    assert sent_sections, "the default-group builder emitted no sections"
    assert sent_sections <= set(live), sorted(sent_sections - set(live))
    assert len(live["custom_objects"]) == len(sent["custom_objects"])


# ---------------------------------------------------------------------------
# Reconciliation: the schema's silences, asserted against real payloads
# ---------------------------------------------------------------------------


def _declared_request_fields(
    schema: dict[str, Any], path: str, method: str
) -> set[str]:
    components = schema["components"]["schemas"]
    op = schema["paths"][path][method]
    node = op["requestBody"]["content"]["application/json"]["schema"]
    body = _follow(components, node) or {}
    return set(body.get("properties") or {})


@pytest.mark.parametrize(
    "contract_key, path, method, payload_fixture",
    [
        (
            "POST /api/automation2/automations",
            "/api/automation2/automations",
            "post",
            "drift_automation",
        ),
        ("POST /api/custom-objects", "/api/custom-objects", "post", "drift_object"),
        (
            "POST /api/permission-group",
            "/api/permission-group",
            "post",
            "drift_permission_group",
        ),
    ],
)
def test_undeclared_fields_match_the_known_omissions(
    request, openapi_schema, contract_key, path, method, payload_fixture
):
    """Every top-level field the CLI sends is either declared in the schema or
    listed in ``KNOWN_SCHEMA_OMISSIONS`` with a reason.

    Fails in both directions on purpose. A field that drops off the list means
    the schema caught up (delete the entry). A field that appears means the CLI
    grew a payload key nobody reconciled against the published contract.
    """
    sent = request.getfixturevalue(payload_fixture)["sent"]
    declared = _declared_request_fields(openapi_schema, path, method)
    known = KNOWN_SCHEMA_OMISSIONS.get(contract_key, {})

    def excused(name: str) -> bool:
        # A leading `*` is the one glob form KNOWN_SCHEMA_OMISSIONS uses
        # (`*_section`), for families of keys the schema is wholesale silent on.
        return name in known or any(
            pat.startswith("*") and name.endswith(pat[1:]) for pat in known
        )

    undeclared = {k for k in sent if k not in declared and not excused(k)}
    assert not undeclared, (
        f"{contract_key}: payload fields neither declared in the live schema nor "
        f"listed in KNOWN_SCHEMA_OMISSIONS: {sorted(undeclared)}"
    )

    stale = {pat for pat in known if not pat.startswith("*") and pat in declared}
    assert not stale, (
        f"{contract_key}: the schema now declares {sorted(stale)} — remove those "
        "KNOWN_SCHEMA_OMISSIONS entries so the omission list stays honest"
    )
