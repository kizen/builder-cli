"""Live guard for the update-time `active`-preservation fix.

The offline golden tests in ``tests/test_automation_payloads.py`` pin the
*payload* `plan_update_automation` builds when a spec omits `active` — they
cannot prove the real API accepts that payload and actually leaves the
automation active. This test closes that gap: it creates a throwaway
automation, flips it active through the explicit `set_active()` path (which
this fix does not touch), plans and applies an update from a spec that says
nothing about `active`, and re-reads the live automation to confirm it is
still active. This is the exact shape of the regression First-Use Feedback
§7/§9 row #12 reported.
"""

from __future__ import annotations

import pytest

from kizen_builder.tools.automations import get_automation, set_active
from kizen_builder.tools.planners.automations import plan_update_automation
from kizen_builder.tools.plans import apply_plan
from tests.drift.conftest import debris_api_name, debris_name

pytestmark = pytest.mark.drift


def test_update_omitting_active_preserves_live_active_automation(drift_client, scratch):
    from kizen_builder.api import automations as auto_api
    from kizen_builder.models.spec import AutomationDef
    from kizen_builder.tools.planners.automations import (
        LiveContext,
        _build_automation_payload,
    )

    api_name = debris_api_name("preserve_active")
    name = debris_name("preserve active")
    spec = AutomationDef.model_validate(
        {
            "api_name": api_name,
            "name": name,
            "type": "global",
            "active": False,
            "steps": [],
        }
    )
    payload = _build_automation_payload(spec, LiveContext())
    created = auto_api.create_automation(drift_client, payload)
    scratch.track(
        "automation",
        created["id"],
        lambda: auto_api.delete_automation(drift_client, created["id"]),
    )

    # Flip it active through the explicit path — unchanged by this fix, and
    # the only way to get a live-active automation to test the fix against.
    set_active(api_name, True, execute=True)
    assert get_automation(api_name)["active"] is True, (
        "set_active did not bring the automation up active; nothing to test"
    )

    # An update spec that says nothing about `active` must not turn a live
    # automation off.
    update_spec = {
        "api_name": api_name,
        "name": name,
        "type": "global",
        "steps": [],
    }
    plan = plan_update_automation(update_spec)
    result = apply_plan(plan)
    assert result.all_ok, [r.message for r in result.results if r.status != "ok"]

    after = get_automation(api_name)
    assert after["active"] is True, (
        "an update spec that omitted `active` deactivated a live automation "
        "— this is the regression First-Use Feedback §7/§9 row #12 reported"
    )
