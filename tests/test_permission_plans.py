"""The five permissions planner entry points: role and permission-group
create/update/delete.

Every planner builds its own `KizenClient` from config, so these go through
`respx` against `FAKE_BASE_URL` — the seam `fake_env` (conftest, autouse)
already wires up — rather than injecting a client. A couple of tests at the
bottom exercise `api.permissions.patch_permission_group` /
`object_update_permission` directly: those two functions are the write
endpoints `_setting_op` routes between, and nothing in the planners or tools
layer calls them (only `apply_plan`, which is generic plan-execution infra
out of scope here), so they need their own coverage.
"""

from __future__ import annotations

import json

import httpx
import respx

from kizen_builder.api import permissions as perm_api
from kizen_builder.api.client import KizenClient
from kizen_builder.config import load_env_config
from kizen_builder.tools.planners.permissions import (
    plan_create_permission_group,
    plan_create_role,
    plan_delete_permission_group,
    plan_delete_role,
    plan_update_role,
)
from kizen_builder.tools.plans import PlanError
from tests.conftest import FAKE_BASE_URL, load_fixture

ROLE_ID = "00000000-0000-4000-8000-000000000101"
GROUP_ID = "00000000-0000-4000-8000-000000000201"
GROUP_ID_2 = "00000000-0000-4000-8000-000000000202"
OBJ_ID = "00000000-0000-4000-8000-000000000301"
FIELD_ID = "00000000-0000-4000-8000-000000000402"
UNKNOWN_GROUP_ID = "00000000-0000-4000-8000-0000000009ff"

ROLE_LIST = load_fixture("permissions/role_list.json")
ROLE_DETAIL = load_fixture("permissions/role_detail.json")
GROUP_LIST = load_fixture("permissions/permission_group_list.json")
GROUP_DETAIL = load_fixture("permissions/permission_group_detail.json")
META = load_fixture("permissions/permissions_meta_data.json")


def _mock_role_list():
    return respx.get(f"{FAKE_BASE_URL}/api/role").mock(
        return_value=httpx.Response(200, json=ROLE_LIST)
    )


def _mock_group_list():
    return respx.get(f"{FAKE_BASE_URL}/api/permission-group").mock(
        return_value=httpx.Response(200, json=GROUP_LIST)
    )


def _mock_role_detail(role_id: str = ROLE_ID, body: dict | None = None):
    return respx.get(f"{FAKE_BASE_URL}/api/role/{role_id}").mock(
        return_value=httpx.Response(200, json=body or ROLE_DETAIL)
    )


def _mock_group_detail(group_id: str = GROUP_ID, body: dict | None = None):
    return respx.get(f"{FAKE_BASE_URL}/api/permission-group/{group_id}").mock(
        return_value=httpx.Response(200, json=body or GROUP_DETAIL)
    )


def _mock_meta():
    return respx.get(f"{FAKE_BASE_URL}/api/permissions/meta-data").mock(
        return_value=httpx.Response(200, json=META)
    )


# ---------------------------------------------------------------------------
# plan_create_role
# ---------------------------------------------------------------------------


@respx.mock
def test_plan_create_role_omits_permissions_key_when_empty():
    """The create endpoint rejects an explicit empty `permissions: []` list
    ("This list may not be empty.") but accepts the key being absent. The
    planner must never send `[]`."""
    _mock_role_list()
    _mock_group_list()

    plan = plan_create_role(name="New Role")

    (op,) = plan.operations
    assert op.action == "create"
    assert op.kind == "role"
    assert op.key == "New Role"
    assert "permissions" not in op.payload
    assert op.payload == {
        "name": "New Role",
        "permission_groups": [],
        "default_for_new_users": False,
    }


@respx.mock
def test_plan_create_role_includes_nonempty_permissions_and_resolves_groups():
    _mock_role_list()
    _mock_group_list()

    plan = plan_create_role(
        name="New Role",
        permissions=["manage_users"],
        permission_group_ids=[GROUP_ID],
        default_for_new_users=True,
    )

    (op,) = plan.operations
    assert op.payload == {
        "name": "New Role",
        "permission_groups": [GROUP_ID],
        "default_for_new_users": True,
        "permissions": ["manage_users"],
    }
    assert op.preview["permission_groups"] == ["Sample Group"]
    assert op.preview["app_permissions"] == 1


@respx.mock
def test_plan_create_role_raises_when_name_already_exists():
    _mock_role_list()
    _mock_group_list()

    try:
        plan_create_role(name="Sales Rep")  # matches ROLE_LIST fixture
        raise AssertionError("expected PlanError")
    except PlanError as exc:
        assert ROLE_ID in str(exc)


@respx.mock
def test_plan_create_role_raises_for_unknown_group_id():
    _mock_role_list()
    _mock_group_list()

    try:
        plan_create_role(name="New Role", permission_group_ids=[UNKNOWN_GROUP_ID])
        raise AssertionError("expected PlanError")
    except PlanError as exc:
        assert UNKNOWN_GROUP_ID in str(exc)


# ---------------------------------------------------------------------------
# plan_update_role
# ---------------------------------------------------------------------------


@respx.mock
def test_plan_update_role_emits_skip_op_when_nothing_changed():
    """Diffing against live state and finding no differences must emit a
    `skip` action, not a no-op PATCH."""
    _mock_role_detail()

    plan = plan_update_role(ROLE_ID, {"name": ROLE_DETAIL["name"]})

    (op,) = plan.operations
    assert op.action == "skip"
    assert op.payload == {}
    assert op.preview["diff"] == "no changes"
    assert "No changes" in plan.summary


@respx.mock
def test_plan_update_role_builds_diff_for_changed_fields_only():
    _mock_role_detail()

    plan = plan_update_role(
        ROLE_ID,
        {
            "name": "Renamed Role",
            "default_for_new_users": ROLE_DETAIL["default_for_new_users"],
        },
    )

    (op,) = plan.operations
    assert op.action == "update"
    assert op.payload == {"name": "Renamed Role"}  # unchanged field is not resent
    assert op.existing_uuid == ROLE_ID
    assert "name" in op.preview["diff"]
    assert "default_for_new_users" not in op.preview["diff"]


# ---------------------------------------------------------------------------
# plan_delete_role
# ---------------------------------------------------------------------------


@respx.mock
def test_plan_delete_role():
    _mock_role_detail()

    plan = plan_delete_role(ROLE_ID)

    (op,) = plan.operations
    assert op.action == "delete"
    assert op.kind == "role"
    assert op.existing_uuid == ROLE_ID
    assert op.key == ROLE_DETAIL["name"]


# ---------------------------------------------------------------------------
# plan_create_permission_group
# ---------------------------------------------------------------------------


@respx.mock
def test_plan_create_permission_group_default_base_posts_full_structure():
    """Create must always carry the full structure — every custom object and
    every section — never just `{name}`."""
    _mock_group_list()
    _mock_group_detail()
    _mock_meta()

    plan = plan_create_permission_group(name="New Group", base="default")

    (op,) = plan.operations
    assert op.action == "create"
    assert op.kind == "permission_group"
    assert op.payload["name"] == "New Group"
    assert "custom_objects" in op.payload
    assert "dashboards_section" in op.payload
    assert "automations_section" in op.payload
    assert "contacts_section" in op.payload
    for key in ("id", "summary", "user_count", "role_count"):
        assert key not in op.payload
    assert op.preview["base"] == "default"
    assert op.preview["custom_objects"] == 1


@respx.mock
def test_plan_create_permission_group_default_base_resets_leaves_to_meta_defaults():
    """`base=default` doesn't just clone the template's shape — it resets
    every leaf's *value* to the meta default, which can differ from the
    template's current value."""
    _mock_group_list()
    _mock_group_detail()
    _mock_meta()

    plan = plan_create_permission_group(name="New Group", base="default")

    (op,) = plan.operations
    # template had manage_automations at view-only; meta default is also
    # "view", so this pins the dict dialect is preserved through a reset.
    assert op.payload["automations_section"]["manage_automations"] == {
        "view": True,
        "edit": False,
        "remove": False,
    }
    # dashboards default True -> highest non-none allowed ("view")
    assert op.payload["dashboards_section"]["view_all_dashboards"] is True


@respx.mock
def test_plan_create_permission_group_clone_base_copies_template_verbatim():
    """`base=clone` copies the template's wire values as-is — no reset."""
    _mock_group_list()
    _mock_group_detail()
    _mock_meta()

    plan = plan_create_permission_group(
        name="Cloned Group", base="clone", template_id=GROUP_ID
    )

    (op,) = plan.operations
    assert op.preview["base"] == "clone"
    assert op.payload["name"] == "Cloned Group"
    # verbatim copy of the source group's contacts_section, dialects intact
    assert op.payload["contacts_section"] == GROUP_DETAIL["contacts_section"]
    assert op.payload["automations_section"] == GROUP_DETAIL["automations_section"]
    for key in ("id", "summary", "user_count", "role_count"):
        assert key not in op.payload


@respx.mock
def test_plan_create_permission_group_raises_when_name_exists():
    _mock_group_list()

    try:
        plan_create_permission_group(name="Sample Group")  # in GROUP_LIST fixture
        raise AssertionError("expected PlanError")
    except PlanError:
        pass


@respx.mock
def test_plan_create_permission_group_raises_when_no_template_available():
    respx.get(f"{FAKE_BASE_URL}/api/permission-group").mock(
        return_value=httpx.Response(200, json={"results": [], "next": None})
    )

    try:
        plan_create_permission_group(name="First Group")
        raise AssertionError("expected PlanError")
    except PlanError as exc:
        assert "shape template" in str(exc)


@respx.mock
def test_plan_create_permission_group_unknown_base_raises():
    _mock_group_list()
    _mock_group_detail()
    _mock_meta()

    try:
        plan_create_permission_group(name="New Group", base="bogus")
        raise AssertionError("expected PlanError")
    except PlanError as exc:
        assert "bogus" in str(exc)


@respx.mock
def test_plan_create_permission_group_settings_build_object_field_and_section_ops():
    """`settings` shaping ops resolve to the two write dialects, and each op
    carries `deferred_parent_object_key` pointing at the group being created
    in the same plan (its id isn't known until apply time)."""
    _mock_group_list()
    _mock_group_detail()
    _mock_meta()

    plan = plan_create_permission_group(
        name="New Group",
        settings=[
            {"type": "object", "object_id": OBJ_ID, "key": "records", "level": "edit"},
            {
                "type": "field",
                "object_id": OBJ_ID,
                "field_id": FIELD_ID,
                "level": "view",
            },
            {
                "type": "section",
                "section_key": "dashboards_section",
                "value": {"enabled": False, "view_all_dashboards": False},
            },
        ],
    )

    create_op, object_op, field_op, section_op = plan.operations

    assert object_op.kind == "permission_setting"
    assert object_op.action == "update"
    assert object_op.deferred_parent_object_key == "New Group"
    assert object_op.payload == {
        "mode": "object_update",
        "body": {
            "custom_object": {"id": OBJ_ID},
            "permission_level": 2,
            "key": "records",
        },
    }

    # A "field" setting only ever carries `field`, never `key` — the branch
    # in `_setting_op` that adds `key` is an `elif`, reachable only for
    # `type: object`, even if a caller mistakenly supplies both.
    assert field_op.deferred_parent_object_key == "New Group"
    assert field_op.payload == {
        "mode": "object_update",
        "body": {
            "custom_object": {"id": OBJ_ID},
            "permission_level": 1,
            "field": {"id": FIELD_ID},
        },
    }

    assert section_op.kind == "permission_setting"
    assert section_op.deferred_parent_object_key == "New Group"
    assert section_op.payload == {
        "mode": "section",
        "body": {
            "dashboards_section": {"enabled": False, "view_all_dashboards": False}
        },
    }
    assert "3 setting(s)" in plan.summary


@respx.mock
def test_plan_create_permission_group_setting_level_as_integer():
    _mock_group_list()
    _mock_group_detail()
    _mock_meta()

    plan = plan_create_permission_group(
        name="New Group",
        settings=[{"type": "object", "object_id": OBJ_ID, "level": 3}],
    )

    _, setting_op = plan.operations
    assert setting_op.payload["body"]["permission_level"] == 3


@respx.mock
def test_plan_create_permission_group_unknown_setting_type_raises():
    _mock_group_list()
    _mock_group_detail()
    _mock_meta()

    try:
        plan_create_permission_group(name="New Group", settings=[{"type": "bogus"}])
        raise AssertionError("expected PlanError")
    except PlanError as exc:
        assert "bogus" in str(exc)


# ---------------------------------------------------------------------------
# plan_delete_permission_group
# ---------------------------------------------------------------------------


@respx.mock
def test_plan_delete_permission_group():
    _mock_group_detail()

    plan = plan_delete_permission_group(GROUP_ID)

    (op,) = plan.operations
    assert op.action == "delete"
    assert op.kind == "permission_group"
    assert op.existing_uuid == GROUP_ID
    assert op.key == GROUP_DETAIL["name"]


# ---------------------------------------------------------------------------
# api.permissions write endpoints — the two dialects `_setting_op` routes
# between. Nothing in the planner or tools layer calls these directly (only
# `apply_plan`, out of scope), so they get their own direct coverage here.
# ---------------------------------------------------------------------------


@respx.mock
def test_patch_permission_group_hits_the_group_endpoint_with_a_full_section():
    route = respx.patch(f"{FAKE_BASE_URL}/api/permission-group/{GROUP_ID}").mock(
        return_value=httpx.Response(200, json={"id": GROUP_ID})
    )
    body = {"dashboards_section": {"enabled": True, "view_all_dashboards": True}}

    with KizenClient(load_env_config()) as client:
        perm_api.patch_permission_group(client, GROUP_ID, body)

    assert route.call_count == 1
    assert json.loads(route.calls.last.request.content) == body


@respx.mock
def test_object_update_permission_hits_the_object_update_endpoint():
    route = respx.patch(
        f"{FAKE_BASE_URL}/api/permission-group/{GROUP_ID}/object-update"
    ).mock(return_value=httpx.Response(200, json={"id": GROUP_ID}))
    body = {
        "custom_object": {"id": OBJ_ID},
        "key": "records",
        "permission_level": 2,
    }

    with KizenClient(load_env_config()) as client:
        perm_api.object_update_permission(client, GROUP_ID, body)

    assert route.call_count == 1
    assert json.loads(route.calls.last.request.content) == body
