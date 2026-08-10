"""Read tools for the per-object saved-view resources: filter groups, quick
filters, and column templates. See ``api.saved_views`` for the endpoint shapes
and ``tools.planners.saved_views`` for the mutation side.
"""

from __future__ import annotations

from typing import Any

from kizen_builder.api import saved_views as sv_api
from kizen_builder.api.client import KizenClient
from kizen_builder.config import load_env_config
from kizen_builder.tools.objects import get_object


def resolve_object_id(object_api_name: str) -> str:
    """UUID of a custom object (or ``client_client``) by api_name."""
    obj = get_object(object_api_name)
    return obj["id"]


def list_saved_views(
    object_api_name: str,
    base: str,
    search: str | None = None,
    ordering: str | None = None,
) -> list[dict[str, Any]]:
    config = load_env_config()
    object_id = resolve_object_id(object_api_name)
    with KizenClient(config) as client:
        return sv_api.list_saved_views(
            client, object_id, base, search=search, ordering=ordering
        )


def find_saved_view(object_api_name: str, base: str, id_or_name: str) -> dict[str, Any]:
    """Resolve a saved view by UUID or by exact name, returning the full detail GET.

    Filter groups' list endpoint returns a leaner shape than the detail GET
    (no ``owner``/``hidden``/``sharing_settings``) — and quick filters' list
    per-item shape is undocumented in the spec — so a name match always does
    one more GET-by-id rather than trusting the list item is full detail.
    """
    config = load_env_config()
    object_id = resolve_object_id(object_api_name)
    with KizenClient(config) as client:
        if _looks_like_uuid(id_or_name):
            return sv_api.get_saved_view(client, object_id, base, id_or_name)
        items = sv_api.list_saved_views(client, object_id, base)
        matches = [i for i in items if i.get("name") == id_or_name]
        if not matches:
            available = [i.get("name") for i in items]
            raise LookupError(
                f"no saved view named '{id_or_name}' on '{object_api_name}'. "
                f"Available: {available}"
            )
        if len(matches) > 1:
            raise LookupError(
                f"'{id_or_name}' matches {len(matches)} saved views on "
                f"'{object_api_name}' — use its UUID instead: "
                f"{[m.get('id') for m in matches]}"
            )
        return sv_api.get_saved_view(client, object_id, base, matches[0]["id"])


def _looks_like_uuid(value: str) -> bool:
    import uuid

    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False
