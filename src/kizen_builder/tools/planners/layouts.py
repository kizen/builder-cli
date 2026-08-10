"""Plan updates to a custom object's record layout.

Layouts are PUT-replace only (Kizen auto-creates the "Standard View" on object
creation), so there's no create path — the planner resolves the target layout's
id from live state and builds the full PUT body. Block ``id``s are injected at
every level (a missing id makes Kizen *merge* rather than replace, leaving
orphaned blocks — see `kizen docs show reference`). Non-``fields`` block types are
passed through opaquely.
"""

from __future__ import annotations

from typing import Any

from kizen_builder.config import load_env_config
from kizen_builder.models.spec import LayoutDef
from kizen_builder.tools.layouts import (
    _fetch_layouts,
    _layout_block_summary,
    inject_layout_ids,
)
from kizen_builder.tools.plans import Plan, PlanError, PlanOperation


def plan_update_layout(object_api_name: str, spec: dict[str, Any] | LayoutDef) -> Plan:
    """Plan a PUT-replace of one record layout from a full config."""
    lo = spec if isinstance(spec, LayoutDef) else LayoutDef.model_validate(spec)
    env = load_env_config().name

    try:
        obj_id, layouts = _fetch_layouts(object_api_name)
    except LookupError as e:
        raise PlanError(str(e)) from e
    if not layouts:
        raise PlanError(f"object '{object_api_name}' has no layouts to update.")

    target = next((x for x in layouts if x.get("name") == lo.name), None)
    if target is None:
        names = ", ".join(repr(x.get("name")) for x in layouts)
        raise PlanError(
            f"object '{object_api_name}' has no layout named {lo.name!r} "
            f"(available: {names})."
        )

    # Inject the required ids at every level before sending.
    new_config = inject_layout_ids([dict(g) for g in lo.config])

    payload: dict[str, Any] = {
        "name": lo.name,
        # Preserve the live layout's active/order/tabs unless the spec overrides.
        "active": target.get("active", True),
        "order": target.get("order", 0.0),
        "config": new_config,
        "tabs": lo.tabs
        if lo.tabs is not None
        else target.get("tabs", {"automations": True}),
    }

    before_blocks = len(_layout_block_summary(target.get("config", [])))
    after_blocks = len(_layout_block_summary(new_config))

    op = PlanOperation(
        action="update",
        kind="layout",
        key=f"{object_api_name}.{lo.name}",
        preview={
            "env": env,
            "object": object_api_name,
            "layout": lo.name,
            "blocks": f"{before_blocks} → {after_blocks}",
        },
        payload=payload,
        existing_uuid=target["id"],
        parent_object_uuid=obj_id,
    )
    return Plan.build(
        env=env,
        summary=f"Replace layout '{lo.name}' on {object_api_name} "
        f"({after_blocks} block(s))",
        operations=[op],
    )
