"""`automations start`: variable-override payload, name validation, and the
client_id-vs-record_id routing for contact automations.

The override wire shape is StartAutomationRequest.variable_overrides — a list
of VariableOverrideRequest ``{variable_name, value}`` where value is a string
the server coerces by the variable's data_type (confirmed against the public
OpenAPI schema and a live start).
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from kizen_builder.tools.automations import start_automation
from tests.conftest import FAKE_BASE_URL

AUTO_ID = "1800a96e-fb22-4ec3-a912-ca1795744b7a"
AUTOS = f"{FAKE_BASE_URL}/api/automation2/automations"


def _mock_automation(*, api_name: str, object_name: str, variables: list[dict]):
    """Mock the list + detail lookups start_automation performs."""
    respx.get(AUTOS).mock(
        return_value=httpx.Response(
            200, json={"results": [{"id": AUTO_ID, "api_name": api_name}], "next": None}
        )
    )
    respx.get(f"{AUTOS}/{AUTO_ID}").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": AUTO_ID,
                "api_name": api_name,
                "revision": 1,
                "active": True,
                "custom_object": {"name": object_name},
                "variables": variables,
                "triggers": [],
                "steps": [],
            },
        )
    )


def _start_route(api_name: str):
    return respx.post(f"{AUTOS}/{api_name}/start").mock(
        return_value=httpx.Response(200, json={"execution": {"id": "exec-123"}})
    )


@respx.mock
def test_variables_become_variable_overrides_with_string_values():
    _mock_automation(
        api_name="form_submission",
        object_name="cd_activity",
        variables=[{"name": "org_match"}, {"name": "llm_notes"}],
    )
    route = _start_route("form_submission")

    result = start_automation(
        "form_submission",
        "rec-1",
        variables={"org_match": True, "llm_notes": "seed text"},
    )

    body = json.loads(route.calls[-1].request.content)
    assert body["record_id"] == "rec-1"
    assert "client_id" not in body
    assert body["variable_overrides"] == [
        {"variable_name": "org_match", "value": "true"},  # bool → "true"
        {"variable_name": "llm_notes", "value": "seed text"},
    ]
    assert result["execution_id"] == "exec-123"


@respx.mock
def test_unknown_variable_name_is_rejected_before_start():
    _mock_automation(
        api_name="form_submission",
        object_name="cd_activity",
        variables=[{"name": "org_match"}],
    )
    route = _start_route("form_submission")

    with pytest.raises(LookupError) as exc:
        start_automation("form_submission", "rec-1", variables={"typo": "x"})

    assert "typo" in str(exc.value)
    assert "org_match" in str(exc.value)  # lists the declared names
    assert not route.called  # never fired the automation


@respx.mock
def test_contact_automation_routes_id_to_client_id():
    _mock_automation(api_name="contact_flow", object_name="client_client", variables=[])
    route = _start_route("contact_flow")

    result = start_automation("contact_flow", "contact-9")

    body = json.loads(route.calls[-1].request.content)
    assert body == {"client_id": "contact-9"}  # NOT record_id
    assert result["client_id"] == "contact-9"
    assert result["record_id"] is None


@respx.mock
def test_no_variables_sends_bare_record_id():
    _mock_automation(
        api_name="form_submission", object_name="cd_activity", variables=[]
    )
    route = _start_route("form_submission")

    start_automation("form_submission", "rec-1")

    body = json.loads(route.calls[-1].request.content)
    assert body == {"record_id": "rec-1"}  # no empty variable_overrides key


def _mock_global_automation(*, api_name: str):
    """Mock a global (record-less) automation — no custom_object."""
    respx.get(AUTOS).mock(
        return_value=httpx.Response(
            200, json={"results": [{"id": AUTO_ID, "api_name": api_name}], "next": None}
        )
    )
    respx.get(f"{AUTOS}/{AUTO_ID}").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": AUTO_ID,
                "api_name": api_name,
                "revision": 1,
                "active": True,
                "custom_object": None,
                "variables": [],
                "triggers": [],
                "steps": [],
            },
        )
    )


@respx.mock
def test_global_automation_starts_without_record():
    _mock_global_automation(api_name="nightly_sync")
    route = _start_route("nightly_sync")

    result = start_automation("nightly_sync")  # no record

    body = json.loads(route.calls[-1].request.content)
    assert body == {}  # neither record_id nor client_id
    assert result["execution_id"] == "exec-123"
    assert result["record_id"] is None and result["client_id"] is None


@respx.mock
def test_record_based_automation_without_record_errors():
    _mock_automation(
        api_name="form_submission", object_name="cd_activity", variables=[]
    )
    route = _start_route("form_submission")

    with pytest.raises(LookupError, match="record-based"):
        start_automation("form_submission")  # missing required record

    assert not route.called


@respx.mock
def test_inactive_automation_errors_before_start():
    """An inactive automation is caught locally, not sent (the API 400s on it)."""
    respx.get(AUTOS).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [{"id": AUTO_ID, "api_name": "global_test"}],
                "next": None,
            },
        )
    )
    respx.get(f"{AUTOS}/{AUTO_ID}").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": AUTO_ID,
                "api_name": "global_test",
                "revision": 1,
                "active": False,
                "custom_object": None,
                "variables": [],
                "triggers": [],
                "steps": [],
            },
        )
    )
    route = _start_route("global_test")

    with pytest.raises(LookupError, match="inactive"):
        start_automation("global_test")

    assert not route.called
