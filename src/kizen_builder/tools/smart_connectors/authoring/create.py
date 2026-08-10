"""Authoring: ``create`` — validate a new connector against live state and
build its payload."""

from __future__ import annotations

from typing import Any

from kizen_builder.api import smart_connectors as sc_api
from kizen_builder.api.client import KizenClient
from kizen_builder.config import load_env_config
from kizen_builder.tools.plans import PlanError
from kizen_builder.tools.smart_connectors.authoring._helpers import (
    _SAMPLE_FILE_SHAPES,
    CONNECTOR_TYPES,
    WEBHOOK_SQL_VERSION,
    _object_lookup,
    _resolved,
)


def plan_create_connector(
    *,
    name: str,
    custom_object: str,
    connector_type: str,
    description: str | None = None,
    cadence: int | None = None,
    activity_object: str | None = None,
    sql_version: str | None = None,
) -> dict[str, Any]:
    """Validate a new connector against live state and return a preview + payload.

    Checks more than the API does: the OpenAPI schema marks only ``name``
    required, but the server also needs ``custom_object`` and
    ``connector_type``, plus ``cadence`` for ``schedule`` and ``activity_object``
    for ``activity``. Enum values (cadence, sql_version) are validated against
    ``/metadata`` so a typo fails here rather than as a bare 400.
    """
    if connector_type not in CONNECTOR_TYPES:
        raise PlanError(
            f"unknown connector_type '{connector_type}'. "
            f"Choose one of: {', '.join(CONNECTOR_TYPES)}"
        )

    config = load_env_config()
    with KizenClient(config) as client:
        by_api, by_id = _object_lookup(client)
        object_id = _resolved(custom_object, by_api, by_id, "custom object")
        meta = sc_api.get_metadata(client)

        clash = next(
            (
                c
                for c in sc_api.list_smart_connectors(client, search=name)
                if (c.get("name") or "").strip().lower() == name.strip().lower()
            ),
            None,
        )
        if clash:
            raise PlanError(
                f"a connector named '{name}' already exists "
                f"(api_name {clash.get('api_name')}, uuid {clash.get('id')})"
            )

        cadences = [str(c[0]) for c in (meta.get("cadence_choices") or []) if c]
        if cadence is not None and cadences and str(cadence) not in cadences:
            raise PlanError(
                f"cadence {cadence} isn't offered. Choose one of: {', '.join(cadences)} (seconds)"
            )
        versions = list(meta.get("sql_versions") or [])
        if sql_version and versions and sql_version not in versions:
            raise PlanError(
                f"sql_version '{sql_version}' isn't offered. Choose one of: {', '.join(versions)}"
            )

        activity_object_id: str | None = None
        activity_object_name: str | None = None
        if connector_type == "activity":
            if not activity_object:
                raise PlanError(
                    "an activity connector needs --activity-object: the activity "
                    "TYPE it listens to (see `kizen activities list`), not a custom object"
                )
            from kizen_builder.api import activities as act_api

            acts = act_api.list_activities(client, show_no_objects_associated=True)
            match = next(
                (
                    a
                    for a in acts
                    if activity_object
                    in (a.get("id"), a.get("api_name"), a.get("name"))
                ),
                None,
            )
            if match is None:
                raise PlanError(
                    f"activity type '{activity_object}' not found. "
                    f"Available: {sorted(a.get('name') or '' for a in acts)}"
                )
            activity_object_id = match["id"]
            activity_object_name = match.get("name")

        if connector_type == "schedule" and cadence is None:
            raise PlanError(
                "a schedule connector needs --cadence (seconds between runs); "
                f"offered: {', '.join(cadences) or 'see `smart-connectors metadata`'}"
            )

        # Webhook connectors only work on 4.1.x, and the failure mode is a bare
        # 500 from sample generation with nothing pointing at the version — so
        # pin it rather than let the server's default decide.
        if connector_type == "webhook":
            if sql_version and sql_version != WEBHOOK_SQL_VERSION:
                raise PlanError(
                    f"a webhook connector needs sql_version "
                    f"{WEBHOOK_SQL_VERSION} — sample generation 500s on every "
                    f"lower version (including the declared {sql_version} floor), "
                    f"with no hint that the version is the problem"
                )
            sql_version = WEBHOOK_SQL_VERSION

    payload: dict[str, Any] = {
        "name": name,
        "custom_object": object_id,
        "connector_type": connector_type,
    }
    if description:
        payload["description"] = description
    if cadence is not None:
        payload["cadence"] = cadence
    if activity_object_id:
        payload["activity_object"] = activity_object_id
    if sql_version:
        payload["sql_version"] = sql_version

    return {
        "env": config.name,
        "payload": payload,
        "preview": {
            "name": name,
            "connector_type": connector_type,
            "custom_object": by_id.get(object_id, object_id),
            "cadence": cadence,
            "activity_object": activity_object_name,
            "sql_version": sql_version,
            "status": "setup (until `smart-connectors activate`)",
        },
        "next_step": (
            "attach a reference file: `smart-connectors set-input <file> "
            f"--connector <api_name>` — {_SAMPLE_FILE_SHAPES.get(connector_type, 'a representative CSV')}"
        ),
    }


def apply_create_connector(payload: dict[str, Any]) -> dict[str, Any]:
    """POST the connector and return the created detail (id/api_name/status)."""
    config = load_env_config()
    with KizenClient(config) as client:
        created = sc_api.create_smart_connector(client, payload)
    draft = created.get("last_draft_script") or {}
    return {
        "id": created.get("id"),
        "api_name": created.get("api_name"),
        "name": created.get("name"),
        "connector_type": created.get("connector_type"),
        "status": created.get("status"),
        "draft_script_id": draft.get("id"),
    }
