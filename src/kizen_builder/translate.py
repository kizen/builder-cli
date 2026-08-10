"""Live→wire translation for automations (GET response → PUT payload).

The automations API reads and writes different dialects:

* GET returns steps with server ``id``s, ``parent_step_id`` linkage, and
  ``parent_condition`` ("yes"/"no"/"") — and returns ``key: null`` (the
  client-supplied keys sent on write are NOT stored). Step UUIDs rotate on
  every PUT, so a GET→edit→PUT cycle must synthesize fresh keys, rewrite
  all id-based cross-references (``parent_step_id``,
  ``go_to_automation_step.step``) to those keys, and complete atomically.
* PUT takes ``key`` / ``parent_key`` / ``parent_yes_no`` linkage, bare
  UUIDs where reads return expanded ``{id, name, …}`` objects, and requires
  sequential trigger ``order`` values (reads return gaps/nulls).
* The server accepts disconnected step graphs without complaint (observed
  live: an automation with three roots and no linkage), so
  :func:`validate_payload` gates every PUT on our side.

Per-type wire knowledge lives in the planner builders
(:mod:`kizen_builder.tools.planners.automations`); this module reuses them
where they exist and falls back to a mechanical strip for types that don't
have a builder yet. The empirical contract is round-trip fidelity:
``PUT(live_to_payload(GET(x)))`` followed by a fresh GET must be a semantic
no-op (see :func:`semantic_diff`), verified by
``kizen automations roundtrip``.
"""

from __future__ import annotations

from typing import Any

from kizen_builder.tools.planners.automations import (
    _STEP_BUILDERS,
    _TRIGGER_BUILDERS,
    _block_field_for,
    _merge_server_state,
    _prefix_for,
    _strip,
)
from kizen_builder.tools.plans import PlanError


class _NoLookupContext:
    """Live data is already fully resolved; any lookup means a translation bug."""

    def __getattr__(self, name: str) -> Any:
        def _fail(*args: Any, **kwargs: Any) -> Any:
            raise PlanError(
                f"live→wire translation unexpectedly needed a live lookup "
                f"({name} {args}); the GET response should already contain UUIDs"
            )

        return _fail


class _NoTargetAuto:
    """Stand-in AutomationDef: builders only touch ``target_object``."""

    target_object = None


_SHIM_CTX = _NoLookupContext()
_SHIM_AUTO = _NoTargetAuto()


# ---------------------------------------------------------------------------
# Key synthesis
# ---------------------------------------------------------------------------


def _sorted_steps(raw: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(raw.get("steps") or [], key=lambda s: s.get("order") or 0)


def _sorted_triggers(raw: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        raw.get("triggers") or [],
        key=lambda t: t.get("order") if t.get("order") is not None else 0,
    )


def synthesize_step_keys(raw: dict[str, Any]) -> dict[str, str]:
    """Map server step UUID → a fresh, readable, unique key."""
    return {
        s["id"]: f"s{i:02d}_{s['step_type']}" for i, s in enumerate(_sorted_steps(raw))
    }


def synthesize_trigger_keys(raw: dict[str, Any]) -> dict[str, str]:
    return {
        t["id"]: f"t{i}_{t['trigger_type']}"
        for i, t in enumerate(_sorted_triggers(raw))
    }


# ---------------------------------------------------------------------------
# live → PUT payload
# ---------------------------------------------------------------------------


def live_to_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw GET automation response into a full PUT payload.

    The payload is a semantic no-op: applying it unchanged must leave the
    automation identical (modulo rotated step/trigger UUIDs and revision).
    Callers that patch a step mutate the returned payload before PUT.
    """
    step_keys = synthesize_step_keys(raw)
    trigger_keys = synthesize_trigger_keys(raw)

    payload: dict[str, Any] = {
        "name": raw["name"],
        "api_name": raw["api_name"],
        "type": raw["type"],
        "active": raw.get("active", False),
        "skip_non_working_days": raw.get("skip_non_working_days", False),
        "return_all_steps_errors": True,
    }
    if raw.get("custom_object"):
        payload["custom_object_id"] = raw["custom_object"]["id"]
    if raw.get("user_description"):
        payload["user_description"] = raw["user_description"]
    if raw.get("error_notification_email") is not None:
        payload["error_notification_email"] = raw["error_notification_email"]

    payload["triggers"] = [
        _live_trigger_to_wire(t, key=trigger_keys[t["id"]], order=i)
        for i, t in enumerate(_sorted_triggers(raw))
    ]
    payload["steps"] = [
        _live_step_to_wire(s, step_keys, trigger_keys) for s in _sorted_steps(raw)
    ]
    # Carries folder/variables/throttles, injects variable ids into
    # initialize_variable steps, stamps last_revision.
    return _merge_server_state(payload, raw)


def _live_step_to_wire(
    step: dict[str, Any],
    step_keys: dict[str, str],
    trigger_keys: dict[str, str],
) -> dict[str, Any]:
    step_type = step["step_type"]
    branch = step.get("parent_condition") or ""
    parent_id = step.get("parent_step_id")

    action_on_failure = step.get("action_on_failure") or "notify_continue"
    if step_type == "condition" and action_on_failure == "notify_continue":
        action_on_failure = "notify_pause"

    p: dict[str, Any] = {
        "key": step_keys[step["id"]],
        "parent_key": step_keys.get(parent_id) if parent_id else None,
        "parent_yes_no": branch,
        "parent_condition": branch,
        "type": step_type,
        "prefix": _prefix_for(step_type),
        "order": step.get("order") or 0,
        "user_description": step.get("user_description") or "",
        "action_on_failure": action_on_failure,
        "should_skip_execution": step.get("should_skip_execution", False),
        "goal_type": step_type == "goal",
    }
    if step.get("description"):
        p["description"] = step["description"]

    cfg_key = _block_field_for(step_type)
    block = dict(step.get(cfg_key) or {})

    if step_type == "go_to_automation_step":
        block = _rewire_go_to(block, step_keys, trigger_keys)

    builder = _STEP_BUILDERS.get(step_type)
    if builder is not None:
        p[cfg_key] = builder(block, _SHIM_AUTO, _SHIM_CTX)
    else:
        p[cfg_key] = _generic_block(block)
    return p


def _rewire_go_to(
    block: dict[str, Any],
    step_keys: dict[str, str],
    trigger_keys: dict[str, str],
) -> dict[str, Any]:
    """Rewrite id-based go_to references to synthesized keys.

    Read shape is ``{step: {id, …}, trigger: {id, …}|null}``; the ids belong
    to the current revision and rotate on PUT, so they must become keys that
    resolve within the payload being sent.
    """
    out = dict(block)
    target = out.pop("step", None)
    if isinstance(target, dict) and target.get("id"):
        target_id = target["id"]
        if target_id not in step_keys:
            raise PlanError(
                f"go_to_automation_step points at step id {target_id} which is "
                "not part of this automation"
            )
        out["step_key"] = step_keys[target_id]
    trig = out.pop("trigger", None)
    if isinstance(trig, dict) and trig.get("id"):
        trig_id = trig["id"]
        if trig_id not in trigger_keys:
            raise PlanError(
                f"go_to_automation_step points at trigger id {trig_id} which is "
                "not part of this automation"
            )
        out["trigger_key"] = trigger_keys[trig_id]
    return out


def _live_trigger_to_wire(
    trigger: dict[str, Any], key: str, order: int
) -> dict[str, Any]:
    trigger_type = trigger["trigger_type"]
    p: dict[str, Any] = {
        "key": key,
        "type": trigger_type,
        "prefix": "trigger",
        "user_description": trigger.get("user_description") or "",
        "should_skip_execution": trigger.get("should_skip_execution", False),
        "order": order,
    }
    if trigger.get("description"):
        p["description"] = trigger["description"]
    if trigger.get("skip_non_working_days") is not None:
        p["skip_non_working_days"] = trigger["skip_non_working_days"]

    cfg_key = f"trigger_{trigger_type}"
    block = dict(trigger.get(cfg_key) or {})
    builder = _TRIGGER_BUILDERS.get(trigger_type)
    if builder is not None:
        p[cfg_key] = builder(block, _SHIM_CTX)
    else:
        p[cfg_key] = _generic_block(block)
    return p


def _generic_block(block: dict[str, Any]) -> dict[str, Any]:
    """Fallback for types without a builder: mechanical read-only strip.

    Deliberately conservative — keeps nested ids and expanded objects.
    Round-trip failures against live are the signal to promote a type to a
    real builder in the planner module.
    """
    return _strip(block)


# ---------------------------------------------------------------------------
# Payload validation (the server does NOT do this)
# ---------------------------------------------------------------------------


def validate_payload(payload: dict[str, Any]) -> list[str]:
    """Structural checks on a PUT payload. Returns a list of problems.

    The live API silently accepts disconnected graphs, duplicate keys, and
    dangling parents — each of which renders as a corrupt automation in the
    UI — so every write path must pass this first.
    """
    problems: list[str] = []
    steps = payload.get("steps") or []
    keys = [s.get("key") for s in steps]
    key_set = set(keys)

    if len(keys) != len(key_set):
        dupes = sorted({k for k in keys if keys.count(k) > 1})
        problems.append(f"duplicate step keys: {dupes}")

    by_key = {s.get("key"): s for s in steps}
    roots = [s for s in steps if not s.get("parent_key")]
    if steps and len(roots) != 1:
        problems.append(
            f"expected exactly 1 root step, found {len(roots)} "
            f"({[s.get('key') for s in roots]})"
        )

    for s in steps:
        pk = s.get("parent_key")
        if pk and pk not in key_set:
            problems.append(f"step '{s.get('key')}' has dangling parent_key '{pk}'")
        branch = s.get("parent_yes_no") or ""
        if branch:
            parent = by_key.get(pk)
            if parent is not None and parent.get("type") not in ("condition", "goal"):
                problems.append(
                    f"step '{s.get('key')}' sets parent_yes_no='{branch}' but its "
                    f"parent '{pk}' is a '{parent.get('type')}', not condition/goal"
                )
        goto = s.get("action_go_to_automation_step")
        if goto and goto.get("step_key"):
            target = by_key.get(goto["step_key"])
            if target is None:
                problems.append(
                    f"step '{s.get('key')}' go_to target '{goto['step_key']}' "
                    "does not exist"
                )
            elif target.get("type") == "initialize_variable":
                problems.append(
                    f"step '{s.get('key')}' go_to targets initialize_variable "
                    f"'{goto['step_key']}' — the server rejects this (400)"
                )

    # Cycle check via parent chain
    for s in steps:
        seen: set[str] = set()
        cur = s.get("key")
        while cur:
            if cur in seen:
                problems.append(f"cycle in parent chain involving '{s.get('key')}'")
                break
            seen.add(cur)
            nxt = by_key.get(cur)
            cur = nxt.get("parent_key") if nxt else None

    # Server rule: initialize_variable steps must all come before any other
    # step ("All Initialize Variable steps should be at the beginning of the
    # automation" — HTTP 400 otherwise).
    init_orders = [
        s.get("order") or 0 for s in steps if s.get("type") == "initialize_variable"
    ]
    other_orders = [
        s.get("order") or 0 for s in steps if s.get("type") != "initialize_variable"
    ]
    if init_orders and other_orders and max(init_orders) > min(other_orders):
        problems.append(
            "initialize_variable steps must all be at the front of the "
            "automation, before every other step (server 400s otherwise)"
        )

    orders = [t.get("order") for t in payload.get("triggers") or []]
    if sorted(orders) != list(range(len(orders))):
        problems.append(f"trigger orders must be sequential from 0: got {orders}")
    return problems


# ---------------------------------------------------------------------------
# Semantic diff (GET-before vs GET-after, modulo volatile fields)
# ---------------------------------------------------------------------------

_VOLATILE_TOP_KEYS = {
    "id",
    "created",
    "updated",
    "revision",
    "number_active",
    "number_paused",
    "number_completed",
    "steps",
    "triggers",
}
# `created` appears on nested definition objects (automation variables,
# webhook extractors, …) that the server recreates wholesale on every PUT.
_VOLATILE_NESTED_KEYS = {"stats", "has_error", "step_error", "created"}
# Derived mirrors of the parent linkage; stale copies corrupt UI rendering
# and their ids rotate, so they are excluded from comparison.
_DERIVED_CONDITION_KEYS = {"yes_steps", "no_steps", "groups"}


def canonicalize(raw: dict[str, Any]) -> dict[str, Any]:
    """Reduce a GET response to a form stable across no-op PUTs.

    Step/trigger UUIDs rotate on every PUT, so steps are identified by
    position in order-sorted sequence and id-based cross-references become
    ``<step:N>`` markers. Nested object ids are dropped (compared by their
    remaining keys) except singleton ``{id: …}`` dicts, which have nothing
    else to compare by.
    """
    steps = _sorted_steps(raw)
    idx = {s["id"]: n for n, s in enumerate(steps)}

    def walk(v: Any) -> Any:
        if isinstance(v, dict):
            out = {}
            for k, val in v.items():
                if k in _VOLATILE_NESTED_KEYS:
                    continue
                if k == "id":
                    if isinstance(val, str) and val in idx:
                        out[k] = f"<step:{idx[val]}>"
                    elif len(v) == 1:
                        out[k] = val
                    continue
                out[k] = walk(val)
            return out
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, str) and v in idx:
            return f"<step:{idx[v]}>"
        return v

    canon_steps = []
    for s in steps:
        c = {
            k: walk(v)
            for k, v in s.items()
            if k not in ("id", "parent_step_id") and k not in _VOLATILE_NESTED_KEYS
        }
        parent_id = s.get("parent_step_id")
        c["parent"] = f"<step:{idx[parent_id]}>" if parent_id in idx else None
        cond = c.get("step_condition")
        if isinstance(cond, dict):
            for derived in _DERIVED_CONDITION_KEYS:
                cond.pop(derived, None)
        canon_steps.append(c)

    canon_triggers = [
        {
            k: walk(v)
            for k, v in t.items()
            if k != "id" and k not in _VOLATILE_NESTED_KEYS
        }
        for t in _sorted_triggers(raw)
    ]

    top = {
        k: walk(v)
        for k, v in raw.items()
        if k not in _VOLATILE_TOP_KEYS and k not in _VOLATILE_NESTED_KEYS
    }
    return {"top": top, "triggers": canon_triggers, "steps": canon_steps}


def semantic_diff(
    before_raw: dict[str, Any], after_raw: dict[str, Any]
) -> list[tuple[str, Any, Any]]:
    """Differences between two GET responses, ignoring volatile fields.

    Returns ``[]`` when the automations are semantically identical —
    the pass condition for a round-trip.
    """
    return _diff(canonicalize(before_raw), canonicalize(after_raw), "")


def _diff(a: Any, b: Any, path: str) -> list[tuple[str, Any, Any]]:
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[tuple[str, Any, Any]] = []
        for k in sorted(set(a) | set(b)):
            sub = f"{path}.{k}" if path else str(k)
            if k not in a:
                out.append((sub, "<absent>", b[k]))
            elif k not in b:
                out.append((sub, a[k], "<absent>"))
            else:
                out.extend(_diff(a[k], b[k], sub))
        return out
    if isinstance(a, list) and isinstance(b, list):
        out = []
        for i in range(max(len(a), len(b))):
            sub = f"{path}[{i}]"
            if i >= len(a):
                out.append((sub, "<absent>", b[i]))
            elif i >= len(b):
                out.append((sub, a[i], "<absent>"))
            else:
                out.extend(_diff(a[i], b[i], sub))
        return out
    if a != b:
        return [(path, a, b)]
    return []
