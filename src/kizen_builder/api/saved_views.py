"""Thin httpx wrappers for the three per-object "saved view" resources:
filter groups, quick filters, and column templates.

All three share one CRUD shape under ``/api/custom-objects/{object_pk}/...``
(list/create at the collection, GET/PUT/PATCH/DELETE at ``{id}``) and the same
``EntityPermission`` sharing-settings block used by dashboards (see
``tools.dashboards.normalize_sharing_settings``). They differ only in:

  - the base path segment (``filter-groups`` / ``quick-filters`` / ``columns``)
  - the wire key for the resource's opaque config blob (``config`` /
    ``filters`` / ``configuration_json``)
  - which ``apply-to-*`` convenience endpoints exist (filter groups: none;
    quick filters: roles + users; columns: roles + users + permission groups)

Endpoints confirmed against the full internal OpenAPI spec (not the repo's
public subset) on 2026-07-20.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from kizen_builder.api.client import KizenClient

FILTER_GROUPS_BASE = "filter-groups"
QUICK_FILTERS_BASE = "quick-filters"
COLUMNS_BASE = "columns"


def _collection_path(object_id: str, base: str) -> str:
    return f"/api/custom-objects/{object_id}/{base}"


def _item_path(object_id: str, base: str, view_id: str) -> str:
    return f"{_collection_path(object_id, base)}/{view_id}"


def list_saved_views(
    client: KizenClient,
    object_id: str,
    base: str,
    search: str | None = None,
    ordering: str | None = None,
) -> list[dict[str, Any]]:
    """GET the collection, transparently paginated (DRF-style envelope)."""
    params: dict[str, Any] = {}
    if search:
        params["search"] = search
    if ordering:
        params["ordering"] = ordering

    items: list[dict[str, Any]] = []
    path: str | None = _collection_path(object_id, base)
    first = True
    while path:
        resp = client.get(path, params=params if first else None)
        first = False
        if isinstance(resp, dict) and "results" in resp:
            items.extend(resp["results"])
            nxt = resp.get("next")
            if nxt:
                parts = urlsplit(nxt)
                path = parts.path + (f"?{parts.query}" if parts.query else "")
            else:
                path = None
        elif isinstance(resp, list):
            items.extend(resp)
            path = None
        else:
            path = None
    return items


def get_saved_view(
    client: KizenClient, object_id: str, base: str, view_id: str
) -> dict[str, Any]:
    return client.get(_item_path(object_id, base, view_id))


def create_saved_view(
    client: KizenClient, object_id: str, base: str, payload: dict[str, Any]
) -> dict[str, Any]:
    return client.post(_collection_path(object_id, base), json=payload)


def update_saved_view(
    client: KizenClient,
    object_id: str,
    base: str,
    view_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return client.patch(_item_path(object_id, base, view_id), json=payload)


def delete_saved_view(
    client: KizenClient, object_id: str, base: str, view_id: str
) -> dict[str, Any]:
    resp = client.delete(_item_path(object_id, base, view_id))
    return resp if isinstance(resp, dict) else {}


def apply_to_roles(
    client: KizenClient, object_id: str, base: str, view_id: str, role_ids: list[str]
) -> dict[str, Any]:
    """POST .../{id}/apply-to-roles. Quick filters and columns only."""
    return client.post(
        f"{_item_path(object_id, base, view_id)}/apply-to-roles",
        json={"role_ids": role_ids},
    )


def apply_to_users(
    client: KizenClient,
    object_id: str,
    base: str,
    view_id: str,
    team_member_ids: list[str],
) -> dict[str, Any]:
    """POST .../{id}/apply-to-users. Quick filters and columns only."""
    return client.post(
        f"{_item_path(object_id, base, view_id)}/apply-to-users",
        json={"team_member_ids": team_member_ids},
    )


def apply_to_permission_groups(
    client: KizenClient,
    object_id: str,
    base: str,
    view_id: str,
    group_ids: list[str],
) -> dict[str, Any]:
    """POST .../{id}/apply-to-permission-groups. Columns only."""
    return client.post(
        f"{_item_path(object_id, base, view_id)}/apply-to-permission-groups",
        json={"permission_group_ids": group_ids},
    )
