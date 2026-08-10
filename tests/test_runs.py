"""Automation runs (executions): endpoint paths + read→display field mapping.

Regression coverage for two bugs fixed in the `runs` command regroup:

1. The single-run detail endpoint was called with a trailing slash
   (`/automation-execution/{id}/`), which 404s with an HTML page; the API
   serves it at `/automation-execution/{id}` (no slash).
2. Both detail and history mapped fields that don't exist on the response
   (`started_at`/`finished_at`, and a flat `type`/`description` on history
   rows), so timestamps and step types/descriptions always came back blank.
   The real fields are `created`/`updated`, `execution_time_ms`, and a nested
   `step`/`trigger` ActionLight.
"""

from __future__ import annotations

import httpx
import respx

from kizen_builder.tools.automations import (
    get_execution,
    get_execution_history,
    list_executions,
)
from tests.conftest import FAKE_BASE_URL, load_fixture

EXEC_ID = "a5fa0b69-cf86-4849-81b2-1521cffe19a4"
EXEC_BASE = f"{FAKE_BASE_URL}/api/automation2/automation-execution"


@respx.mock
def test_get_execution_uses_no_trailing_slash_and_maps_timestamps():
    detail = load_fixture("executions/detail_form_submission.json")
    # The route is registered WITHOUT a trailing slash. A request to the old
    # trailing-slash path would not match this mock (and 404s in production).
    route = respx.get(f"{EXEC_BASE}/{EXEC_ID}").mock(
        return_value=httpx.Response(200, json=detail)
    )

    result = get_execution(EXEC_ID)

    assert route.called
    assert result["status"] == "completed"
    assert result["automation_api_name"] == "form_submission"
    assert result["record_id"] == "51612b78-723e-451b-aede-f8037d2523d4"
    # created → started_at, updated → finished_at (no started_at/finished_at
    # exists on the response).
    assert result["started_at"] == detail["created"]
    assert result["finished_at"] == detail["updated"]


@respx.mock
def test_get_execution_history_maps_nested_step_and_duration():
    history = load_fixture("executions/history_form_submission.json")
    respx.get(f"{EXEC_BASE}/{EXEC_ID}/history").mock(
        return_value=httpx.Response(200, json=history)
    )

    rows = get_execution_history(EXEC_ID)

    assert len(rows) == 3

    trigger_row, init_row, code_row = rows

    # A trigger firing: type/description come from the nested ActionLight.
    assert trigger_row["kind"] == "trigger"
    assert trigger_row["type"] == "manual"
    assert trigger_row["description"] == "Manual"

    # A completed step surfaces its duration and start/finish timestamps.
    assert init_row["kind"] == "step"
    assert init_row["type"] == "initialize_variable"
    assert init_row["duration_ms"] == 25
    assert init_row["started_at"] == "2026-03-18T10:29:31.500000-05:00"
    assert init_row["finished_at"] == "2026-03-18T10:29:31.525000-05:00"

    # A failed step falls back to error_description when error is null.
    assert code_row["status"] == "failed"
    assert code_row["error"] == "NameError: name 'foo' is not defined"


@respx.mock
def test_list_executions_maps_start_time_not_created():
    """The list item shape uses start_time/completed (AutomationExecutionList),
    not the created/updated of the single-run detail — mapping started_at from
    `created` silently produced blanks."""
    auto_id = "b1c2d3e4-0000-4000-8000-000000000001"
    respx.get(f"{FAKE_BASE_URL}/api/automation2/automations").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [{"id": auto_id, "api_name": "form_submission"}],
                "next": None,
            },
        )
    )
    respx.get(EXEC_BASE).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": EXEC_ID,
                        "status": "completed",
                        "start_time": "2026-03-18T10:29:31.364611-05:00",
                        "completed": "2026-03-18T10:30:03.444480-05:00",
                        "created": None,
                        "record": {"id": "51612b78-723e-451b-aede-f8037d2523d4"},
                        "automation": {"api_name": "form_submission"},
                        "debug_mode": "off",
                    }
                ],
                "next": None,
            },
        )
    )

    rows = list_executions("form_submission")

    assert len(rows) == 1
    row = rows[0]
    assert row["started_at"] == "2026-03-18T10:29:31.364611-05:00"
    assert row["finished_at"] == "2026-03-18T10:30:03.444480-05:00"
    assert row["record_id"] == "51612b78-723e-451b-aede-f8037d2523d4"
