"""Read tools for automations in a Kizen environment."""

from __future__ import annotations

import contextlib
from typing import Any

from kizen_builder.api import automations as auto_api
from kizen_builder.api import messages as messages_api
from kizen_builder.api.client import KizenAPIError, KizenClient
from kizen_builder.config import load_env_config

_NOTIFY_MEMBER_ACTION_FIELDS = (
    "action_notify_member_via_email",
    "action_notify_member_via_text",
)


def _reconcile_notify_member_message_links(
    client: KizenClient, raw: dict[str, Any]
) -> None:
    """Stamp automation_step back onto notify_member_via_email/text steps'
    message resources after a PUT.

    See :func:`kizen_builder.api.messages.set_automation_message_step` — the
    PUT that creates/clones the message doesn't set this FK on its own.
    Self-healing (safe to call after every write, including ones untouched
    by this PUT): best-effort, a failure here shouldn't fail the step write.
    """
    for step in raw.get("steps") or []:
        step_id = step.get("id")
        if not step_id:
            continue
        for field in _NOTIFY_MEMBER_ACTION_FIELDS:
            block = step.get(field)
            message_id = block.get("id") if isinstance(block, dict) else None
            if message_id:
                with contextlib.suppress(KizenAPIError):
                    messages_api.set_automation_message_step(
                        client, message_id, step_id
                    )


def list_automations(folder: str | None = None) -> list[dict[str, Any]]:
    """Return a summary of every automation in the configured env.

    ``folder`` filters to automations in one folder, matched by folder name
    or UUID (the root folder is a real folder named `<business_root>`, not
    an absence of one — every automation's `folder` is always populated).
    """
    config = load_env_config()
    with KizenClient(config) as client:
        raw = auto_api.list_automations(client)

    out: list[dict[str, Any]] = []
    for a in raw:
        f = a.get("folder") or {}
        out.append(
            {
                "env": config.name,
                "id": a.get("id"),
                "name": a.get("name"),
                "api_name": a.get("api_name"),
                "type": a.get("type"),
                "active": a.get("active"),
                "revision": a.get("revision"),
                "custom_object_id": (a.get("custom_object") or {}).get("id"),
                "custom_object_name": (a.get("custom_object") or {}).get("name"),
                "folder_id": f.get("id"),
                "folder_name": f.get("name"),
                "number_active": a.get("number_active"),
                "number_paused": a.get("number_paused"),
                "number_completed": a.get("number_completed"),
            }
        )

    if folder:
        matched = [a for a in out if folder in (a["folder_id"], a["folder_name"])]
        if not matched:
            available = sorted({a["folder_name"] for a in out if a["folder_name"]})
            raise LookupError(f"folder '{folder}' not found. Available: {available}")
        out = matched
    return out


def list_llm_models() -> list[dict[str, Any]]:
    """Flatten the automations metadata endpoint's LLM catalog into one row
    per (provider, model) — the live source for `call_llm`'s `model_name` +
    `business_plugin_app_id` pairing (see automation.md "LLM & extraction
    destinations"). `business_plugin_app_id` is `None` for `kizen/*` native
    models, which don't need one.
    """
    config = load_env_config()
    with KizenClient(config) as client:
        meta = auto_api.get_metadata(client)

    rows: list[dict[str, Any]] = []
    for provider in (meta.get("llm") or {}).get("provider_model_details") or []:
        plugin_app = provider.get("plugin_app") or {}
        provider_name = provider.get("provider_name")
        bpa_id = plugin_app.get("id") if provider_name != "kizen" else None
        for model in provider.get("models") or []:
            usage = model.get("usage") or {}
            rows.append(
                {
                    "provider_name": provider_name,
                    "model_value": model.get("model_value"),
                    "model_label": model.get("model_label"),
                    "business_plugin_app_id": bpa_id,
                    "supports_call": (usage.get("text") or {}).get("call"),
                    "supports_decision": (usage.get("text") or {}).get("decision"),
                    "supports_extraction": (usage.get("image") or {}).get("extraction"),
                    "supports_transcription": (usage.get("audio") or {}).get(
                        "transcription"
                    ),
                    "is_deprecated": model.get("is_deprecated"),
                    "suggested_replacement": model.get("suggested_replacement"),
                }
            )
    return rows


def get_automation(api_name: str) -> dict[str, Any]:
    """Return one automation in full, including triggers and steps."""
    config = load_env_config()
    with KizenClient(config) as client:
        listing = auto_api.list_automations(client)
        match = next((a for a in listing if a.get("api_name") == api_name), None)
        if match is None:
            raise LookupError(f"no automation with api_name '{api_name}'")
        detail = auto_api.get_automation(client, match["id"])

    triggers = [
        {
            "id": t.get("id"),
            "trigger_type": t.get("trigger_type"),
            "description": t.get("description"),
        }
        for t in (detail.get("triggers") or [])
    ]

    steps = []
    for s in detail.get("steps") or []:
        cond = s.get("step_condition")
        steps.append(
            {
                "id": s.get("id"),
                "step_type": s.get("step_type"),
                "order": s.get("order"),
                "description": s.get("description"),
                "parent_step_id": s.get("parent_step_id"),
                "parent_condition": s.get("parent_condition"),
                "yes_step_ids": [x.get("id") for x in (cond.get("yes_steps") or [])]
                if cond
                else None,
                "no_step_ids": [x.get("id") for x in (cond.get("no_steps") or [])]
                if cond
                else None,
            }
        )

    return {
        "env": config.name,
        "id": detail.get("id"),
        "name": detail.get("name"),
        "api_name": detail.get("api_name"),
        "type": detail.get("type"),
        "active": detail.get("active"),
        "revision": detail.get("revision"),
        "custom_object": detail.get("custom_object"),
        "triggers": triggers,
        "steps": sorted(steps, key=lambda s: s.get("order") or 0),
        "raw": detail,
    }


def roundtrip_automation(api_name: str, execute: bool = False) -> dict[str, Any]:
    """GET → translate → (optionally) PUT unchanged → GET → semantic diff.

    The empirical fidelity test for the live→wire translator: a PUT of the
    translated payload must be a semantic no-op. Returns the payload, any
    structural validation problems, and — when executed — the drift between
    the before/after GET responses (empty list = PASS).
    """
    from kizen_builder.translate import (
        live_to_payload,
        semantic_diff,
        validate_payload,
    )

    config = load_env_config()
    with KizenClient(config) as client:
        listing = auto_api.list_automations(client)
        match = next((a for a in listing if a.get("api_name") == api_name), None)
        if match is None:
            raise LookupError(f"no automation with api_name '{api_name}'")
        before = auto_api.get_automation(client, match["id"])
        payload = live_to_payload(before)
        problems = validate_payload(payload)
        result: dict[str, Any] = {
            "env": config.name,
            "api_name": api_name,
            "id": match["id"],
            "revision_before": before.get("revision"),
            "n_steps": len(payload.get("steps") or []),
            "n_triggers": len(payload.get("triggers") or []),
            "validation_problems": problems,
            "payload": payload,
            "executed": False,
        }
        if not execute or problems:
            return result
        auto_api.update_automation(
            client,
            match["id"],
            payload,
            last_revision=payload.get("last_revision"),
        )
        after = auto_api.get_automation(client, match["id"])
        result["executed"] = True
        result["revision_after"] = after.get("revision")
        result["drift"] = [
            {"path": p, "before": a, "after": b}
            for p, a, b in semantic_diff(before, after)
        ]
    return result


def _fetch_raw(client: KizenClient, api_name: str) -> dict[str, Any]:
    listing = auto_api.list_automations(client)
    match = next((a for a in listing if a.get("api_name") == api_name), None)
    if match is None:
        raise LookupError(f"no automation with api_name '{api_name}'")
    return auto_api.get_automation(client, match["id"])


def show_automation(api_name: str) -> dict[str, Any]:
    """The automation as a translated wire payload — synthesized step keys
    included — for tree rendering and as the source of step-edit handles."""
    from kizen_builder.translate import live_to_payload

    config = load_env_config()
    with KizenClient(config) as client:
        raw = _fetch_raw(client, api_name)
    return {
        "env": config.name,
        "api_name": api_name,
        "id": raw["id"],
        "revision": raw.get("revision"),
        "active": raw.get("active"),
        "name": raw.get("name"),
        "custom_object_name": (raw.get("custom_object") or {}).get("name"),
        "payload": live_to_payload(raw),
    }


def patch_steps(
    api_name: str,
    mutate: Any,
    execute: bool = False,
) -> dict[str, Any]:
    """The one loop every step-level verb runs through.

    GET → translate → ``mutate(payload, raw)`` (in-memory graph surgery;
    returns a report) → validate the graph → with ``execute``, PUT atomically
    (``last_revision`` guards against concurrent edits), re-GET, and report
    the before/after semantic diff as evidence of exactly what changed.
    """
    from kizen_builder.translate import (
        live_to_payload,
        semantic_diff,
        validate_payload,
    )

    config = load_env_config()
    with KizenClient(config) as client:
        before = _fetch_raw(client, api_name)
        payload = live_to_payload(before)
        report = mutate(payload, before)
        problems = validate_payload(payload)
        result: dict[str, Any] = {
            "env": config.name,
            "api_name": api_name,
            "id": before["id"],
            "revision_before": before.get("revision"),
            "report": report,
            "validation_problems": problems,
            "payload": payload,
            "executed": False,
        }
        if problems or not execute:
            return result
        auto_api.update_automation(
            client,
            before["id"],
            payload,
            last_revision=payload.get("last_revision"),
        )
        after = auto_api.get_automation(client, before["id"])
        _reconcile_notify_member_message_links(client, after)
        result["executed"] = True
        result["revision_after"] = after.get("revision")
        result["diff"] = [
            {"path": p, "before": a, "after": b}
            for p, a, b in semantic_diff(before, after)
        ]
    return result


def _patch_field(api_name: str, mutate: Any, execute: bool = False) -> dict[str, Any]:
    """A lighter sibling of `patch_steps` for flipping one top-level field
    (``active``, ``folder``) without requiring a full AutomationDef spec.

    Same GET -> mutate -> PUT loop, but skips step-graph validation (the
    step graph itself isn't touched) and reports a before/after value pair
    instead of a full semantic diff.
    """
    from kizen_builder.translate import live_to_payload

    config = load_env_config()
    with KizenClient(config) as client:
        before = _fetch_raw(client, api_name)
        payload = live_to_payload(before)
        field, value_before, value_after = mutate(payload)
        result: dict[str, Any] = {
            "env": config.name,
            "api_name": api_name,
            "id": before["id"],
            "revision_before": before.get("revision"),
            "field": field,
            "before": value_before,
            "after": value_after,
            "no_op": value_before == value_after,
            "executed": False,
        }
        if not execute:
            return result
        auto_api.update_automation(
            client,
            before["id"],
            payload,
            last_revision=payload.get("last_revision"),
        )
        after = auto_api.get_automation(client, before["id"])
        _reconcile_notify_member_message_links(client, after)
        result["executed"] = True
        result["revision_after"] = after.get("revision")
    return result


def set_active(api_name: str, active: bool, execute: bool = False) -> dict[str, Any]:
    """Flip an automation's `active` flag without re-authoring its full spec."""

    def mutate(payload: dict[str, Any]) -> tuple[str, Any, Any]:
        before = payload.get("active", False)
        payload["active"] = active
        return "active", before, active

    return _patch_field(api_name, mutate, execute)


def move_to_folder(
    api_name: str, folder_id: str | None, folder_name: str | None, execute: bool = False
) -> dict[str, Any]:
    """Move one automation into a folder (or to the root if folder_id is None).

    Confirmed wire mechanism (2026-07-22): the write dialect is a
    bare, nullable `folder_id` — NOT the `folder: {id, name}` shape a live
    read returns, which this function previously round-tripped verbatim
    (ticket 20260720-174419). That shape PUTs fine (200, revision bumps) but
    is silently ignored server-side — `folder` is read-only/expanded-for-
    display, the same "reads expand, writes take a bare id" pattern
    documented elsewhere in this codebase (e.g. field_to_modify,
    target_custom_object). Verified with a direct PUT: `folder_id` set to a
    real folder stuck on the next GET, where the old `folder: {id,name}`
    payload left the automation at `<business_root>` despite the 200.
    """

    def mutate(payload: dict[str, Any]) -> tuple[str, Any, Any]:
        before = payload.pop("folder", None)
        payload["folder_id"] = folder_id
        after = {"id": folder_id, "name": folder_name} if folder_id else None
        return "folder", before, after

    return _patch_field(api_name, mutate, execute)


def list_folders() -> list[dict[str, Any]]:
    """Return every automation folder in the configured env.

    Confirmed live — see api/automations.py's folders section.
    """
    config = load_env_config()
    with KizenClient(config) as client:
        return auto_api.list_folders(client)


def list_subfolders(identifier: str) -> list[dict[str, Any]]:
    """Return the subfolders of one folder (by id or name).

    Confirmed live — see api/automations.py's folders section.
    """
    config = load_env_config()
    with KizenClient(config) as client:
        folders = auto_api.list_folders(client)
        match = next(
            (f for f in folders if identifier in (f.get("id"), f.get("name"))), None
        )
        if match is None:
            available = [f.get("name") for f in folders]
            raise LookupError(
                f"folder '{identifier}' not found. Available: {available}"
            )
        return auto_api.list_subfolders(client, match["id"])


def build_wire_step(
    spec: dict[str, Any], payload: dict[str, Any], target_object: str | None
) -> dict[str, Any]:
    """Build one wire step from a spec-shaped dict (same shapes as
    ``automations create`` step specs: field_refs, api_names, or raw wire).
    Linkage fields are ignored here — placement belongs to insert_step.
    """
    from kizen_builder.models.spec import AutomationDef, AutomationStepDef
    from kizen_builder.tools.planners.automations import (
        LiveContext,
        _build_step_payload,
    )
    from kizen_builder.tools.steps import synthesize_key

    spec = dict(spec)
    for linkage in ("parent_key", "parent_branch"):
        spec.pop(linkage, None)
    spec["order"] = 0  # placeholder; insert_step assigns real placement
    spec.setdefault("key", synthesize_key(payload, spec["step_type"]))
    step_def = AutomationStepDef.model_validate(spec)
    auto = AutomationDef(
        name=payload["name"],
        api_name=payload["api_name"],
        type=payload["type"],
        target_object=target_object,
    )
    return _build_step_payload(step_def, auto, LiveContext())


def normalize_step_patch(
    patch: dict[str, Any],
    step_type: str,
    payload: dict[str, Any],
    target_object: str | None,
) -> dict[str, Any]:
    """Run a patch's config block through the type's read→write builder.

    Lets `steps edit` accept the same authoring shapes as create specs
    (field_refs, api_names) as well as raw wire dicts — builders are
    idempotent on wire shapes.
    """
    from kizen_builder.models.spec import AutomationDef
    from kizen_builder.tools.planners.automations import (
        _STEP_BUILDERS,
        LiveContext,
        _block_field_for,
    )

    cfg_key = _block_field_for(step_type)
    builder = _STEP_BUILDERS.get(step_type)
    if cfg_key in patch and builder is not None and isinstance(patch[cfg_key], dict):
        auto = AutomationDef(
            name=payload["name"],
            api_name=payload["api_name"],
            type=payload["type"],
            target_object=target_object,
        )
        patch[cfg_key] = builder(dict(patch[cfg_key]), auto, LiveContext())
    return patch


def _override_value(value: Any) -> str | None:
    """Coerce an override value to the string the API expects (nullable).

    The wire type is a string the server re-parses by the variable's
    data_type, so booleans go as lowercase ``true``/``false`` and numbers as
    their str(); ``None`` stays null. Strings pass through untouched.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    return str(value)


def start_automation(
    api_name: str,
    record_id: str | None = None,
    *,
    client_id: str | None = None,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Trigger an automation on one entity, optionally seeding variables.

    ``variables`` is a ``{name: value}`` map (e.g. from ``--var``); it's
    validated against the automation's declared variables and translated to
    the API's ``variable_overrides`` list. The entity id is routed to
    ``client_id`` for contact (``client_client``) automations and
    ``record_id`` otherwise, so callers pass one id and don't have to know
    which field the object needs. Returns the execution ID.
    """
    config = load_env_config()
    with KizenClient(config) as client:
        listing = auto_api.list_automations(client)
        match = next((a for a in listing if a.get("api_name") == api_name), None)
        if match is None:
            raise LookupError(f"no automation with api_name '{api_name}'")
        detail = auto_api.get_automation(client, match["id"])

        # An inactive automation can't be started — the API answers a bare
        # HTTP 400 ("automation must be active"). Catch it here so the caller
        # gets an actionable message instead of a raw wire error.
        if not detail.get("active"):
            raise LookupError(
                f"automation '{api_name}' is inactive — activate it in Kizen "
                "before starting it (the API rejects starts on inactive "
                "automations)."
            )

        overrides: list[dict[str, Any]] | None = None
        if variables:
            declared = {v.get("name"): v for v in (detail.get("variables") or [])}
            unknown = [name for name in variables if name not in declared]
            if unknown:
                known = ", ".join(sorted(n for n in declared if n)) or "(none)"
                raise LookupError(
                    f"automation '{api_name}' has no variable(s): "
                    f"{', '.join(unknown)}. Declared variables: {known}"
                )
            overrides = [
                {"variable_name": name, "value": _override_value(val)}
                for name, val in variables.items()
            ]

        # Contacts are addressed by client_id, custom-object records by
        # record_id. Route the single caller-supplied id accordingly unless
        # the caller was explicit.
        obj = detail.get("custom_object") or {}
        is_record_based = bool(obj)
        if is_record_based and record_id is None and client_id is None:
            raise LookupError(
                f"automation '{api_name}' is record-based (object "
                f"'{obj.get('name')}') — pass --record <uuid>. Only global "
                "(record-less) automations can start without a record."
            )
        is_contact = obj.get("name") == "client_client"
        if is_contact and record_id is not None and client_id is None:
            client_id, record_id = record_id, None

        resp = auto_api.start_automation(
            client,
            api_name,
            record_id=record_id,
            client_id=client_id,
            variable_overrides=overrides,
        )

    execution = resp.get("execution")
    exec_id = execution.get("id") if isinstance(execution, dict) else execution
    return {
        "env": config.name,
        "execution_id": exec_id,
        "record_id": record_id,
        "client_id": client_id,
        "variable_overrides": overrides,
        "raw": resp,
    }


def get_execution(execution_id: str) -> dict[str, Any]:
    """Return details for one automation execution."""
    config = load_env_config()
    with KizenClient(config) as client:
        raw = auto_api.get_execution(client, execution_id)
    record = raw.get("record") or {}
    automation = raw.get("automation") or {}
    # The API has no started_at/finished_at; it exposes `created` (when the
    # execution began) and `updated` (last state change ≈ finish for a
    # completed run). Mirror list_executions, which maps started_at ← created.
    return {
        "env": config.name,
        "execution_id": raw.get("id"),
        "status": raw.get("status"),
        "automation_api_name": automation.get("api_name")
        or raw.get("automation_api_name"),
        "record_id": record.get("id") or raw.get("record_id"),
        "started_at": raw.get("created"),
        "finished_at": raw.get("updated"),
        "raw": raw,
    }


def list_executions(api_name: str, limit: int = 25) -> list[dict[str, Any]]:
    """Return recent executions for an automation, looked up by api_name."""
    config = load_env_config()
    with KizenClient(config) as client:
        listing = auto_api.list_automations(client)
        match = next((a for a in listing if a.get("api_name") == api_name), None)
        if match is None:
            raise LookupError(f"no automation with api_name '{api_name}'")
        raw = auto_api.list_executions(client, match["id"], limit=limit)
    out = []
    for r in raw:
        record = r.get("record") or {}
        automation = r.get("automation") or {}
        # The list item shape (AutomationExecutionList) uses start_time /
        # completed, NOT the `created`/`updated` of the single-run detail —
        # reading `created` here always produced a blank started_at.
        out.append(
            {
                "execution_id": r.get("id"),
                "status": r.get("status"),
                "automation_api_name": automation.get("api_name") or api_name,
                "record_id": record.get("id"),
                "started_at": r.get("start_time"),
                "finished_at": r.get("completed"),
                "debug_mode": r.get("debug_mode"),
            }
        )
    return out


def get_execution_history(execution_id: str) -> list[dict[str, Any]]:
    """Return step-by-step history for one automation execution."""
    config = load_env_config()
    with KizenClient(config) as client:
        entries = auto_api.get_execution_history(client, execution_id)
    out = []
    for e in entries:
        # A history row is either a trigger firing or a step executing; the
        # human-readable type/description live in that nested ActionLight,
        # not at the row top level (the old flat reads always came back None).
        trigger = e.get("trigger") or {}
        step = e.get("step") or {}
        source = trigger if trigger else step
        out.append(
            {
                "kind": "trigger" if trigger else "step",
                "type": source.get("type"),
                "description": source.get("description"),
                "status": e.get("status"),
                # execution_time_ms is the step's wall-clock duration; created
                # ≈ when it started, updated ≈ when it finished.
                "duration_ms": e.get("execution_time_ms"),
                "started_at": e.get("created"),
                "finished_at": e.get("updated"),
                "error": e.get("error") or e.get("error_description"),
                "detailed_log": e.get("detailed_log"),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Execution control — pause/resume/cancel/skip-and-resume/debug-*. Runtime
# actions on an execution's own state (not a schema mutation), same category
# as `start_automation` above: confirm-free by standing decision, no
# plan/preview gate. Confirmed live (2026-07-22) for pause/
# resume/cancel against a real delayed execution; debug-* wired from the
# public schema but not live-exercised (see api/automations.py).
# ---------------------------------------------------------------------------


def _execution_status_action(execution_id: str, action: Any) -> dict[str, Any]:
    """Shared before/after wrapper for pause/resume/cancel: fetch the
    execution, run `action(client, execution_id, body)`, re-fetch to report
    the resulting status (the action endpoints themselves return no useful
    body)."""
    config = load_env_config()
    with KizenClient(config) as client:
        before = auto_api.get_execution(client, execution_id)
        body = auto_api.execution_action_body(before)
        action(client, execution_id, body)
        after = auto_api.get_execution(client, execution_id)
    return {
        "env": config.name,
        "execution_id": execution_id,
        "status_before": before.get("status"),
        "status_after": after.get("status"),
    }


def pause_execution(execution_id: str) -> dict[str, Any]:
    """Pause a running automation execution."""
    return _execution_status_action(execution_id, auto_api.pause_execution)


def resume_execution(execution_id: str) -> dict[str, Any]:
    """Resume a paused automation execution."""
    return _execution_status_action(execution_id, auto_api.resume_execution)


def cancel_execution(execution_id: str) -> dict[str, Any]:
    """Cancel an automation execution. Irreversible."""
    return _execution_status_action(execution_id, auto_api.cancel_execution)


def skip_and_resume_execution(
    execution_id: str, skip_step_id: str, continue_with_branch: str | None = None
) -> dict[str, Any]:
    """Resume an execution paused on a step failure by skipping that step."""
    config = load_env_config()
    with KizenClient(config) as client:
        before = auto_api.get_execution(client, execution_id)
        auto_api.skip_and_resume_execution(
            client, execution_id, skip_step_id, continue_with_branch
        )
        after = auto_api.get_execution(client, execution_id)
    return {
        "env": config.name,
        "execution_id": execution_id,
        "status_before": before.get("status"),
        "status_after": after.get("status"),
    }


def debug_sendit(execution_id: str) -> dict[str, Any]:
    """Run a debug-mode execution to completion."""
    return _execution_status_action(execution_id, auto_api.debug_sendit)


def debug_rerun(execution_id: str, step_id: str) -> dict[str, Any]:
    """Re-execute one step of an execution; no subsequent steps scheduled."""
    config = load_env_config()
    with KizenClient(config) as client:
        result = auto_api.debug_rerun(client, execution_id, step_id)
    return {
        "env": config.name,
        "execution_id": execution_id,
        "step_id": step_id,
        "result": result,
    }


def debug_restart(execution_id: str, step_id: str) -> dict[str, Any]:
    """Restart an execution from a step; subsequent steps ARE scheduled."""
    config = load_env_config()
    with KizenClient(config) as client:
        result = auto_api.debug_restart(client, execution_id, step_id)
    return {
        "env": config.name,
        "execution_id": execution_id,
        "step_id": step_id,
        "result": result,
    }


def debug_step(
    execution_id: str,
    action: str,
    history_id: str,
    continue_with_branch: str | None = None,
) -> dict[str, Any]:
    """Skip or execute one step of a debug-mode execution."""
    config = load_env_config()
    with KizenClient(config) as client:
        result = auto_api.debug_step(
            client, execution_id, action, history_id, continue_with_branch
        )
    return {
        "env": config.name,
        "execution_id": execution_id,
        "history_id": history_id,
        "result": result,
    }


# ---------------------------------------------------------------------------
# Diagnostics — modification history / failure history, per automation.
# Confirmed live (2026-07-22).
# ---------------------------------------------------------------------------


def get_modification_history(
    api_name: str,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    event_type: list[str] | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    """Return an automation's modification history (who changed what, when)."""
    config = load_env_config()
    with KizenClient(config) as client:
        return auto_api.get_modification_history(
            client,
            api_name,
            date_from=date_from,
            date_to=date_to,
            event_type=event_type,
            search=search,
        )


def get_failures_history(api_name: str) -> list[dict[str, Any]]:
    """Return an automation's execution failure history."""
    config = load_env_config()
    with KizenClient(config) as client:
        return auto_api.get_failures_history(client, api_name)
