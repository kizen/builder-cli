"""Live guard for the execution-history-orphaning bug: editing an automation
must not silently reassign a step's or trigger's server `id`.

`semantic_diff` (the round-trip fidelity check in `test_roundtrip_automations.py`)
deliberately treats `id` as non-semantic — it diffs steps by position, not by
id — which is exactly why the original bug went unnoticed: a full round-trip
could report zero drift while every step got a brand-new id underneath. This
test checks the one thing that check doesn't: that a step/trigger's `id`
itself survives a write.

Ids are compared per-step (keyed by `key`, which is stable across the PUT),
not as before/after sets — a set comparison can't tell a preserved id apart
from a permutation (step A's id landing on step B), since both leave the set
unchanged.
"""

from __future__ import annotations

import pytest

from kizen_builder.api import automations as auto_api
from kizen_builder.translate import live_to_payload

pytestmark = pytest.mark.drift


def test_unchanged_steps_and_triggers_keep_their_id_across_a_put(
    drift_client, drift_automation
):
    automation_id = drift_automation["uuid"]
    before = auto_api.get_automation(drift_client, automation_id)
    payload = live_to_payload(before)
    before_step_id_by_key = {s["key"]: s["id"] for s in payload["steps"]}
    before_trigger_id_by_key = {t["key"]: t["id"] for t in payload["triggers"]}

    auto_api.update_automation(
        drift_client,
        automation_id,
        payload,
        last_revision=payload["last_revision"],
    )

    after = auto_api.get_automation(drift_client, automation_id)
    after_payload = live_to_payload(after)
    after_step_id_by_key = {s["key"]: s["id"] for s in after_payload["steps"]}
    after_trigger_id_by_key = {t["key"]: t["id"] for t in after_payload["triggers"]}

    assert after_step_id_by_key == before_step_id_by_key, (
        "a step's id changed (or moved to a different step) across a no-op "
        "PUT — this orphans that step's execution history in the Kizen UI"
    )
    assert after_trigger_id_by_key == before_trigger_id_by_key, (
        "a trigger's id changed (or moved to a different trigger) across a no-op PUT"
    )
