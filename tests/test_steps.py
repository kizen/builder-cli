"""Tests for step-level graph surgery (tools/steps.py).

Every mutation here was also exercised live against a disposable test env:
chain/branch/leaf inserts, splice removals with
branch inheritance and go_to retargeting, cascade subtree removal, and the
server rules the validator encodes (go_to may not target initialize_variable;
initialize_variable steps must lead the automation).
"""

from __future__ import annotations

import pytest

from kizen_builder.tools.plans import PlanError
from kizen_builder.tools.steps import (
    children_of,
    edit_step,
    find_step,
    insert_step,
    remove_step,
    subtree_keys,
    synthesize_key,
)
from kizen_builder.translate import live_to_payload, validate_payload
from tests.conftest import load_fixture


@pytest.fixture()
def kitchen() -> dict:
    """Fresh translated kitchen-sink payload per test (mutations allowed)."""
    return live_to_payload(load_fixture("automations/kitchen_sink_triggers.raw.json"))


def _key_of(payload: dict, step_type: str, idx: int = 0) -> str:
    return [s for s in payload["steps"] if s["type"] == step_type][idx]["key"]


def _mk_stop(payload: dict) -> dict:
    return {
        "key": synthesize_key(payload, "stop_execution"),
        "type": "stop_execution",
        "prefix": "action",
        "parent_yes_no": "",
        "parent_condition": "",
        "order": 0,
        "action_on_failure": "notify_continue",
        "should_skip_execution": False,
        "goal_type": False,
        "user_description": "",
        "action_stop_execution": {},
    }


def test_find_step_unknown_key_raises(kitchen: dict) -> None:
    with pytest.raises(PlanError, match="no step with key"):
        find_step(kitchen, "s99_nope")


def test_remove_linear_step_splices(kitchen: dict) -> None:
    delay = _key_of(kitchen, "delay")
    dead = find_step(kitchen, delay)
    kids_before = [c["key"] for c in children_of(kitchen, delay)]
    report = remove_step(kitchen, delay)
    assert report["removed"] == [delay]
    for kid in kids_before:
        assert find_step(kitchen, kid)["parent_key"] == dead["parent_key"]
    assert validate_payload(kitchen) == []


def test_remove_branch_head_inherits_branch(kitchen: dict) -> None:
    """Removing the first step of a yes/no branch moves its child into the
    same branch position (live-proven: the UI renders the branch intact)."""
    head = next(
        s
        for s in kitchen["steps"]
        if s.get("parent_yes_no")
        and s["type"] not in ("condition", "goal")
        and children_of(kitchen, s["key"], branch="")
    )
    child = children_of(kitchen, head["key"], branch="")[0]
    assert not child.get("parent_yes_no")
    remove_step(kitchen, head["key"])
    assert child["parent_key"] == head["parent_key"]
    assert child["parent_yes_no"] == head["parent_yes_no"]
    assert validate_payload(kitchen) == []


def test_remove_condition_with_children_refuses(kitchen: dict) -> None:
    cond = next(
        s["key"]
        for s in kitchen["steps"]
        if s["type"] == "condition" and children_of(kitchen, s["key"])
    )
    with pytest.raises(PlanError, match="orphan its yes/no branches"):
        remove_step(kitchen, cond)


def test_remove_cascade_takes_whole_subtree(kitchen: dict) -> None:
    cond = next(
        s["key"]
        for s in kitchen["steps"]
        if s["type"] == "condition" and children_of(kitchen, s["key"])
    )
    doomed = set(subtree_keys(kitchen, cond))
    assert len(doomed) > 1
    report = remove_step(kitchen, cond, cascade=True)
    assert set(report["removed"]) == doomed
    remaining = {s["key"] for s in kitchen["steps"]}
    assert not doomed & remaining
    assert validate_payload(kitchen) == []


def test_remove_retargets_gotos(kitchen: dict) -> None:
    delay = _key_of(kitchen, "delay")
    parent = find_step(kitchen, delay)["parent_key"]
    goto = _mk_stop(kitchen)
    goto["key"] = "s99_go_to_automation_step"
    goto["type"] = "go_to_automation_step"
    del goto["action_stop_execution"]
    goto["action_go_to_automation_step"] = {"step_key": delay}
    leaf = max(kitchen["steps"], key=lambda s: s["order"])
    insert_step(kitchen, goto, parent_key=leaf["key"], adopt_children=False)

    if find_step(kitchen, parent)["type"] == "initialize_variable":
        # Live-discovered server rule: go_to may not land on an
        # initialize_variable step, so the splice must refuse.
        with pytest.raises(PlanError, match="initialize_variable"):
            remove_step(kitchen, delay)
    else:
        report = remove_step(kitchen, delay)
        assert report["retargeted_gotos"] == [goto["key"]]
        assert goto["action_go_to_automation_step"]["step_key"] == parent


def test_insert_into_chain_adopts_children(kitchen: dict) -> None:
    delay = _key_of(kitchen, "delay")
    kids_before = [c["key"] for c in children_of(kitchen, delay)]
    new = _mk_stop(kitchen)
    report = insert_step(kitchen, new, parent_key=delay)
    assert report["adopted"] == kids_before
    for kid in kids_before:
        assert find_step(kitchen, kid)["parent_key"] == new["key"]
    orders = sorted(s["order"] for s in kitchen["steps"])
    assert orders == list(range(len(kitchen["steps"])))
    assert validate_payload(kitchen) == []


def test_insert_into_branch(kitchen: dict) -> None:
    cond = next(
        s["key"]
        for s in kitchen["steps"]
        if s["type"] == "condition" and children_of(kitchen, s["key"], "yes")
    )
    yes_before = [c["key"] for c in children_of(kitchen, cond, "yes")]
    new = _mk_stop(kitchen)
    report = insert_step(kitchen, new, parent_key=cond, branch="yes")
    assert new["parent_yes_no"] == "yes"
    assert set(report["adopted"]) == set(yes_before)
    for kid in yes_before:
        moved = find_step(kitchen, kid)
        assert moved["parent_key"] == new["key"]
        assert moved["parent_yes_no"] == ""
    assert validate_payload(kitchen) == []


def test_insert_branch_under_non_condition_refuses(kitchen: dict) -> None:
    delay = _key_of(kitchen, "delay")
    with pytest.raises(PlanError, match="condition or goal"):
        insert_step(kitchen, _mk_stop(kitchen), parent_key=delay, branch="yes")


def test_insert_root(kitchen: dict) -> None:
    old_root = next(s for s in kitchen["steps"] if s["parent_key"] is None)
    new = _mk_stop(kitchen)
    insert_step(kitchen, new, parent_key=None)
    assert new["parent_key"] is None
    assert old_root["parent_key"] == new["key"]
    assert new["order"] == 0
    # NB: a stop_execution root is graph-valid but init-var placement now
    # fails — initialize_variable steps must lead the automation.
    problems = validate_payload(kitchen)
    assert problems == [
        "initialize_variable steps must all be at the front of the "
        "automation, before every other step (server 400s otherwise)"
    ]


def test_edit_step_merges_and_reports(kitchen: dict) -> None:
    delay = _key_of(kitchen, "delay")
    changes = edit_step(kitchen, delay, {"user_description": "note"})
    assert "user_description" in changes
    assert find_step(kitchen, delay)["user_description"] == "note"


def test_edit_step_key_and_type_frozen(kitchen: dict) -> None:
    delay = _key_of(kitchen, "delay")
    with pytest.raises(PlanError, match="cannot be changed"):
        edit_step(kitchen, delay, {"key": "renamed"})
    with pytest.raises(PlanError, match="cannot be changed"):
        edit_step(kitchen, delay, {"type": "condition"})


def test_validator_flags_goto_to_initialize_variable(kitchen: dict) -> None:
    init = _key_of(kitchen, "initialize_variable")
    goto = _mk_stop(kitchen)
    goto["type"] = "go_to_automation_step"
    del goto["action_stop_execution"]
    goto["action_go_to_automation_step"] = {"step_key": init}
    leaf = max(kitchen["steps"], key=lambda s: s["order"])
    insert_step(kitchen, goto, parent_key=leaf["key"], adopt_children=False)
    problems = validate_payload(kitchen)
    assert any("initialize_variable" in p and "go_to" in p for p in problems)
