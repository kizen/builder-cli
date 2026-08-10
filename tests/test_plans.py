"""Plan serialization round-trip and apply_plan execution semantics."""

from __future__ import annotations

import httpx
import respx

from kizen_builder.tools import plans as plan_tools
from kizen_builder.tools.plans import Plan, PlanOperation
from tests.conftest import FAKE_BASE_URL


def _field_op(**overrides) -> PlanOperation:
    base = {
        "action": "create",
        "kind": "field",
        "key": "invoice.total",
        "preview": {"env": "testenv", "api_name": "total"},
        "payload": {"name": "total", "display_name": "Total", "field_type": "money"},
        "parent_object_uuid": "11111111-1111-4111-8111-111111111111",
    }
    base.update(overrides)
    return PlanOperation(**base)


def test_plan_json_round_trip():
    plan = Plan.build(env="testenv", summary="test", operations=[_field_op()])
    text = plan_tools.plan_to_json(plan)
    restored = plan_tools.plan_from_json(text)
    assert restored.id == plan.id
    assert restored.env == plan.env
    assert restored.operations[0].payload == plan.operations[0].payload
    assert (
        restored.operations[0].parent_object_uuid
        == plan.operations[0].parent_object_uuid
    )


@respx.mock
def test_apply_create_field_posts_and_records_uuid():
    route = respx.post(
        f"{FAKE_BASE_URL}/api/custom-objects/11111111-1111-4111-8111-111111111111/fields"
    ).mock(return_value=httpx.Response(200, json={"id": "new-field-uuid"}))
    plan = Plan.build(env="testenv", summary="test", operations=[_field_op()])

    result = plan_tools.apply_plan(plan)

    assert route.call_count == 1
    (r,) = result.results
    assert r.status == "ok"
    assert r.server_uuid == "new-field-uuid"
    assert result.all_ok


@respx.mock
def test_apply_failure_is_recorded_not_raised():
    respx.post(
        f"{FAKE_BASE_URL}/api/custom-objects/11111111-1111-4111-8111-111111111111/fields"
    ).mock(return_value=httpx.Response(400, json={"detail": "nope"}))
    plan = Plan.build(env="testenv", summary="test", operations=[_field_op()])

    result = plan_tools.apply_plan(plan)

    (r,) = result.results
    assert r.status == "failed"
    assert "nope" in (r.message or "")
    assert not result.all_ok


@respx.mock
def test_apply_internal_error_is_recorded_not_raised():
    """A non-API failure mid-op (here: a field op with no parent uuid, which
    _execute rejects as a planning bug) is recorded as failed, not raised."""
    plan = Plan.build(
        env="testenv",
        summary="t",
        operations=[_field_op(key="invoice.total", parent_object_uuid=None)],
    )

    result = plan_tools.apply_plan(plan)  # must not raise

    (r,) = result.results
    assert r.status == "failed"
    assert "PlanError" in (r.message or "")
    assert not result.all_ok


@respx.mock
def test_apply_continues_after_mid_batch_internal_failure():
    """An internal failure on one op doesn't abort the batch: independent ops
    before and after it still run, and the report is complete."""
    p1 = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa"
    p3 = "cccccccc-3333-4333-8333-cccccccccccc"
    route1 = respx.post(f"{FAKE_BASE_URL}/api/custom-objects/{p1}/fields").mock(
        return_value=httpx.Response(200, json={"id": "field-1"})
    )
    route3 = respx.post(f"{FAKE_BASE_URL}/api/custom-objects/{p3}/fields").mock(
        return_value=httpx.Response(200, json={"id": "field-3"})
    )
    ops = [
        _field_op(key="obj_a.f1", parent_object_uuid=p1),
        _field_op(key="obj_b.f2", parent_object_uuid=None),  # internal failure
        _field_op(key="obj_c.f3", parent_object_uuid=p3),
    ]

    result = plan_tools.apply_plan(
        Plan.build(env="testenv", summary="t", operations=ops)
    )

    assert route1.call_count == 1
    assert route3.call_count == 1
    assert [r.status for r in result.results] == ["ok", "failed", "ok"]
    assert not result.all_ok


@respx.mock
def test_apply_deferred_parent_resolved_from_earlier_op():
    obj_route = respx.post(f"{FAKE_BASE_URL}/api/custom-objects").mock(
        return_value=httpx.Response(200, json={"id": "created-obj-uuid"})
    )
    field_route = respx.post(
        f"{FAKE_BASE_URL}/api/custom-objects/created-obj-uuid/fields"
    ).mock(return_value=httpx.Response(200, json={"id": "created-field-uuid"}))

    ops = [
        PlanOperation(
            action="create",
            kind="object",
            key="invoice",
            preview={},
            payload={"name": "invoice", "object_name": "Invoices"},
        ),
        _field_op(parent_object_uuid=None, deferred_parent_object_key="invoice"),
    ]
    result = plan_tools.apply_plan(
        Plan.build(env="testenv", summary="t", operations=ops)
    )

    assert obj_route.call_count == 1
    assert field_route.call_count == 1
    assert [r.status for r in result.results] == ["ok", "ok"]


@respx.mock
def test_apply_child_ops_skipped_when_parent_fails():
    respx.post(f"{FAKE_BASE_URL}/api/custom-objects").mock(
        return_value=httpx.Response(400, json={"detail": "invalid object"})
    )
    ops = [
        PlanOperation(
            action="create",
            kind="object",
            key="invoice",
            preview={},
            payload={"name": "invoice"},
        ),
        _field_op(parent_object_uuid=None, deferred_parent_object_key="invoice"),
        # prefix-cascade path: no deferred key, but key is namespaced under the object
        _field_op(
            key="invoice.subtotal",
            parent_object_uuid=None,
            payload={"name": "subtotal", "field_type": "money"},
        ),
    ]
    result = plan_tools.apply_plan(
        Plan.build(env="testenv", summary="t", operations=ops)
    )

    statuses = {r.key: r.status for r in result.results}
    assert statuses["invoice"] == "failed"
    assert statuses["invoice.total"] == "skipped"
    assert statuses["invoice.subtotal"] == "skipped"


@respx.mock
def test_apply_automation_update_puts_previewed_payload_verbatim():
    """The plan builder assembles the full PUT body (incl. last_revision);
    apply must send it as-is — no refetch, no server-side reassembly."""
    import json

    payload = {"name": "X", "api_name": "x", "steps": [], "last_revision": 7}
    route = respx.put(f"{FAKE_BASE_URL}/api/automation2/automations/auto-uuid").mock(
        return_value=httpx.Response(200, json={"id": "auto-uuid"})
    )
    # No GET route registered: a revision refetch would blow up the test.
    op = PlanOperation(
        action="update",
        kind="automation",
        key="x",
        preview={},
        payload=payload,
        existing_uuid="auto-uuid",
    )
    result = plan_tools.apply_plan(
        Plan.build(env="testenv", summary="t", operations=[op])
    )

    assert route.call_count == 1
    assert json.loads(route.calls[0].request.content) == payload
    assert result.all_ok


@respx.mock
def test_apply_skip_ops_never_hit_the_api():
    plan = Plan.build(
        env="testenv",
        summary="t",
        operations=[
            _field_op(
                action="skip",
                payload={},
                existing_uuid="22222222-2222-4222-8222-222222222222",
            )
        ],
    )
    result = plan_tools.apply_plan(plan)  # no respx routes: any call would error
    (r,) = result.results
    assert r.status == "skipped"
    assert result.all_ok
