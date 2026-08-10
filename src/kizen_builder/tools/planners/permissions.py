"""Plan creation/update/deletion for roles and permission groups.

Roles are simple: name + a list of app-permission flags + a set of
permission-group ids + a default-for-new-users flag. Permission groups are
created from a full default structure (see
:mod:`kizen_builder.tools.permission_builder`) and then optionally shaped by
``permission_setting`` operations in the same plan.
"""

from __future__ import annotations

import copy
from typing import Any

from kizen_builder.api import permissions as perm_api
from kizen_builder.api.client import KizenClient
from kizen_builder.config import load_env_config
from kizen_builder.tools.permission_builder import build_default_group_payload
from kizen_builder.tools.permissions import LEVELS_BY_NAME
from kizen_builder.tools.plans import Plan, PlanError, PlanOperation


def _client() -> KizenClient:
    return KizenClient(load_env_config())


# ---------------------------------------------------------------------------
# roles
# ---------------------------------------------------------------------------


def plan_create_role(
    name: str,
    permissions: list[str] | None = None,
    permission_group_ids: list[str] | None = None,
    default_for_new_users: bool = False,
) -> Plan:
    env = load_env_config().name
    with _client() as c:
        existing = next(
            (r for r in perm_api.list_roles(c) if r.get("name") == name), None
        )
        if existing is not None:
            raise PlanError(
                f"role '{name}' already exists (uuid {existing['id']}). "
                "Use plan_update_role instead."
            )
        groups = {g["id"]: g["name"] for g in perm_api.list_permission_groups(c)}

    group_ids = permission_group_ids or []
    unknown = [g for g in group_ids if g not in groups]
    if unknown:
        raise PlanError(
            f"permission group id(s) not found: {unknown}. Available: {list(groups)}"
        )

    payload: dict[str, Any] = {
        "name": name,
        "permission_groups": group_ids,
        "default_for_new_users": default_for_new_users,
    }
    # The create endpoint rejects an explicit empty ``permissions`` list
    # ("This list may not be empty.") but accepts the key being absent
    # (stored as []). Only send it when non-empty.
    if permissions:
        payload["permissions"] = permissions
    op = PlanOperation(
        action="create",
        kind="role",
        key=name,
        preview={
            "env": env,
            "name": name,
            "permission_groups": [groups[g] for g in group_ids],
            "default_for_new_users": default_for_new_users,
            "app_permissions": len(permissions or []),
        },
        payload=payload,
    )
    return Plan.build(env=env, summary=f"Create role '{name}'", operations=[op])


def plan_update_role(role_id: str, changes: dict[str, Any]) -> Plan:
    env = load_env_config().name
    with _client() as c:
        current = perm_api.get_role(c, role_id)

    payload: dict[str, Any] = {}
    diff: dict[str, Any] = {}
    for field in ("name", "permissions", "permission_groups", "default_for_new_users"):
        if field in changes and changes[field] != current.get(field):
            payload[field] = changes[field]
            diff[field] = (current.get(field), changes[field])

    action = "update" if payload else "skip"
    op = PlanOperation(
        action=action,  # type: ignore[arg-type]
        kind="role",
        key=current.get("name") or role_id,
        preview={
            "env": env,
            "role": current.get("name"),
            "diff": {k: f"{v[0]} → {v[1]}" for k, v in diff.items()} or "no changes",
        },
        payload=payload,
        existing_uuid=role_id,
    )
    summary = (
        f"Update role '{current.get('name')}' ({len(diff)} change(s))"
        if diff
        else f"No changes to role '{current.get('name')}'"
    )
    return Plan.build(env=env, summary=summary, operations=[op])


def plan_delete_role(role_id: str) -> Plan:
    env = load_env_config().name
    with _client() as c:
        current = perm_api.get_role(c, role_id)
    op = PlanOperation(
        action="delete",
        kind="role",
        key=current.get("name") or role_id,
        preview={"env": env, "role": current.get("name"), "id": role_id},
        existing_uuid=role_id,
    )
    return Plan.build(
        env=env, summary=f"Delete role '{current.get('name')}'", operations=[op]
    )


# ---------------------------------------------------------------------------
# permission groups
# ---------------------------------------------------------------------------


def plan_create_permission_group(
    name: str,
    base: str = "default",
    template_id: str | None = None,
    settings: list[dict[str, Any]] | None = None,
) -> Plan:
    """Plan a new permission group.

    ``base='default'`` builds a fresh group at Kizen's default access levels;
    ``base='clone'`` copies ``template_id`` (or the first existing group) as-is.
    ``settings`` is an optional list of shaping ops applied after creation:

    * ``{"type": "object", "object_id", "key", "level"}``
    * ``{"type": "field", "object_id", "field_id", "level"}``
    * ``{"type": "section", "section_key", "value": {..full section dict..}}``
    """
    env = load_env_config().name
    with _client() as c:
        groups = perm_api.list_permission_groups(c)
        if any(g["name"] == name for g in groups):
            raise PlanError(f"permission group '{name}' already exists.")
        if not groups:
            raise PlanError(
                "no existing permission group to use as a shape template; "
                "create the first group in the Kizen UI."
            )
        tmpl_id = template_id or groups[0]["id"]
        template = perm_api.get_permission_group(c, tmpl_id)
        meta = perm_api.get_permissions_meta_data(c)

    if base == "default":
        payload = build_default_group_payload(name, template, meta)
    elif base == "clone":
        payload = copy.deepcopy(template)
        for k in ("id", "summary", "user_count", "role_count", "created", "updated"):
            payload.pop(k, None)
        payload["name"] = name
    else:
        raise PlanError(f"unknown base {base!r} (expected 'default' or 'clone')")

    ops = [
        PlanOperation(
            action="create",
            kind="permission_group",
            key=name,
            preview={
                "env": env,
                "name": name,
                "base": base,
                "custom_objects": len(payload.get("custom_objects", [])),
            },
            payload=payload,
        )
    ]
    for i, s in enumerate(settings or []):
        ops.append(_setting_op(name, i, s))

    summary = f"Create permission group '{name}' (base={base})"
    if settings:
        summary += f" + {len(settings)} setting(s)"
    return Plan.build(env=env, summary=summary, operations=ops)


def _setting_op(group_key: str, idx: int, s: dict[str, Any]) -> PlanOperation:
    """Build a permission_setting op that resolves the group id at apply time."""
    stype = s.get("type")
    if stype in ("object", "field"):
        level = s["level"]
        level_int = LEVELS_BY_NAME[level] if isinstance(level, str) else int(level)
        body: dict[str, Any] = {
            "custom_object": {"id": s["object_id"]},
            "permission_level": level_int,
        }
        if stype == "field":
            body["field"] = {"id": s["field_id"]}
        elif "key" in s:
            body["key"] = s["key"]
        target = s.get("field_id") or s.get("key") or s["object_id"]
        preview = {"target": f"{stype}:{target}", "level": level}
        payload = {"mode": "object_update", "body": body}
    elif stype == "section":
        preview = {"target": f"section:{s['section_key']}", "value": s["value"]}
        payload = {"mode": "section", "body": {s["section_key"]: s["value"]}}
    else:
        raise PlanError(f"unknown setting type {stype!r}")

    return PlanOperation(
        action="update",
        kind="permission_setting",
        key=f"{group_key}.setting[{idx}]",
        preview=preview,
        payload=payload,
        deferred_parent_object_key=group_key,
    )


def plan_delete_permission_group(group_id: str) -> Plan:
    env = load_env_config().name
    with _client() as c:
        current = perm_api.get_permission_group(c, group_id)
    op = PlanOperation(
        action="delete",
        kind="permission_group",
        key=current.get("name") or group_id,
        preview={"env": env, "group": current.get("name"), "id": group_id},
        existing_uuid=group_id,
    )
    return Plan.build(
        env=env,
        summary=f"Delete permission group '{current.get('name')}'",
        operations=[op],
    )
