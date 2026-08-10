"""Discover the Kizen environments available to this checkout.

Primary source is the central credential store
(``$XDG_CONFIG_HOME/kizen/credentials.toml``); the working directory's
``.kizen/profile`` pin marks which one is active here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dotenv import dotenv_values, find_dotenv

from kizen_builder import profiles


def list_envs(dotenv_path: Path | None = None) -> list[dict[str, Any]]:
    """Return the environments configured for this checkout.

    Each result has ``label``, ``base_url``, ``business_id``, ``complete``,
    ``pinned`` (is this the directory's active profile), and ``source``
    (``"profile"`` for the central store, ``"legacy-env"`` for ``.env``).
    """
    pin = profiles.load_pin()
    pinned_name = pin.profile if pin else None

    stored = profiles.list_profiles()
    if stored:
        return [
            {
                "label": creds.name,
                "base_url": creds.base_url,
                "business_id": creds.business_id,
                "complete": bool(creds.api_key and creds.business_id and creds.user_id),
                "pinned": creds.name == pinned_name,
                "source": "profile",
            }
            for creds in stored
        ]

    # Legacy fallback: a worktree-local .env with unprefixed keys.
    values = (
        dotenv_values(dotenv_path)
        if dotenv_path
        else dotenv_values(find_dotenv(usecwd=True))
    )
    if not values.get("API_KEY") or not values.get("BUSINESS_ID"):
        return []

    return [
        {
            "label": (values.get("KIZEN_ENV") or "default").lower(),
            "base_url": (values.get("BASE_URL") or profiles.DEFAULT_BASE_URL).rstrip(
                "/"
            ),
            "business_id": values["BUSINESS_ID"],
            "complete": all(
                values.get(k) for k in ("API_KEY", "BUSINESS_ID", "USER_ID")
            ),
            "pinned": pinned_name is None,
            "source": "legacy-env",
        }
    ]
