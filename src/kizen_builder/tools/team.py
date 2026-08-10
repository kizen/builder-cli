"""Team member read tools."""

from __future__ import annotations

from typing import Any

from kizen_builder.api import team as team_api
from kizen_builder.api.client import KizenClient
from kizen_builder.config import load_env_config


def search_team(name: str, limit: int = 25) -> list[dict[str, Any]]:
    """Search team members by name or email, returning up to ``limit`` results."""
    config = load_env_config()
    with KizenClient(config) as client:
        raw = team_api.search_team(client, name, limit=limit)
    return [
        {
            "id": m.get("id"),
            "full_name": m.get("full_name")
            or f"{m.get('first_name', '')} {m.get('last_name', '')}".strip(),
            "email": m.get("email"),
            "title": m.get("title"),
        }
        for m in raw
    ]
