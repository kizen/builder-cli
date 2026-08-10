"""Team member reads against the Kizen API."""

from __future__ import annotations

from typing import Any

from kizen_builder.api.client import KizenClient


def search_team(
    client: KizenClient,
    name: str,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """GET /api/team/typeahead?search=<name> — fast text search over team members."""
    result = client.get(
        "/api/team/typeahead",
        params={"search": name, "page_size": min(limit, 100)},
    )
    if isinstance(result, list):
        return result[:limit]
    return list(result.get("results", []))[:limit]


def list_roles(client: KizenClient) -> list[dict[str, Any]]:
    """GET /api/role — list the business's roles ({id, name, ...})."""
    resp = client.get("/api/role")
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict) and "results" in resp:
        return list(resp["results"])
    return []
