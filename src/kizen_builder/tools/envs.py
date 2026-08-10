"""Discover the Kizen environments available to this checkout.

Primary source is the central credential store
(``$XDG_CONFIG_HOME/kizen/credentials.toml``); the working directory's
``.kizen/profile`` pin marks which one is active here.
"""

from __future__ import annotations

from typing import Any

from kizen_builder import profiles


def list_envs() -> list[dict[str, Any]]:
    """Return the environments configured for this checkout.

    Each result has ``label``, ``base_url``, ``business_id``, ``complete``,
    ``pinned`` (is this the directory's active profile), and ``source``
    (always ``"profile"`` — the central store is the only source).
    """
    pin = profiles.load_pin()
    pinned_name = pin.profile if pin else None

    return [
        {
            "label": creds.name,
            "base_url": creds.base_url,
            "business_id": creds.business_id,
            "complete": bool(creds.api_key and creds.business_id and creds.user_id),
            "pinned": creds.name == pinned_name,
            "source": "profile",
        }
        for creds in profiles.list_profiles()
    ]
