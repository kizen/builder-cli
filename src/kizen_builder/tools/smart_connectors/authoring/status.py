"""Authoring: connector status — the ``operational`` flip a live run needs,
and the silent-failure trap of running against a non-operational connector."""

from __future__ import annotations

from typing import Any

from kizen_builder.api import smart_connectors as sc_api
from kizen_builder.api.client import KizenClient
from kizen_builder.config import load_env_config
from kizen_builder.tools.plans import PlanError
from kizen_builder.tools.smart_connectors.authoring._helpers import _connector_ref

CONNECTOR_STATUSES = ("setup", "operational", "need_attention", "inactive")


def plan_set_status(connector: str, status: str) -> dict[str, Any]:
    """Preview a status change. ``operational`` is what a live run requires."""
    if status not in CONNECTOR_STATUSES:
        raise PlanError(
            f"unknown status '{status}'. Choose one of: {', '.join(CONNECTOR_STATUSES)}"
        )
    config = load_env_config()
    with KizenClient(config) as client:
        detail = sc_api.get_smart_connector(client, connector)

    live = (detail.get("live_script") or {}).get("id")
    return {
        "env": config.name,
        "connector": _connector_ref(detail),
        "connector_api_name": detail.get("api_name"),
        "from_status": detail.get("status"),
        "to_status": status,
        "changed": detail.get("status") != status,
        "has_live_script": bool(live),
        "load_steps": len((detail.get("flow") or {}).get("loads") or []),
    }


def apply_set_status(plan: dict[str, Any]) -> dict[str, Any]:
    config = load_env_config()
    with KizenClient(config) as client:
        updated = sc_api.update_smart_connector(
            client, plan["connector"], {"status": plan["to_status"]}
        )
    return {
        "connector": updated.get("api_name") or plan["connector_api_name"],
        "status": updated.get("status"),
    }
