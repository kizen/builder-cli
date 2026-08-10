"""Resolve the active Kizen environment's credentials.

Credentials come from a **Central store** located at
``$XDG_CONFIG_HOME/kizen/credentials.toml`` keyed by profile name (see
:mod:`kizen_builder.profiles`).

Which profile is used is decided *positionally* — by the working directory's
``.kizen/profile`` pin — not by a mutable global "active profile". Resolution
order for the profile name:

    --profile CLI override  >  $KIZEN_PROFILE  >  .kizen/profile pin  >  $KIZEN_ENV

The pin also records the expected ``business_id``; whatever path selected the
profile, the resolved credentials' ``business_id`` must match it or we refuse.
That checksum is the hard guarantee that a command cannot act against the wrong
environment from a pinned directory. The canonical identity of a Kizen
environment is its ``business_id``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

from kizen_builder import profiles

# Set once by the CLI root callback (``--profile``); read during resolution so
# the ~30 no-arg ``load_env_config()`` call sites don't need a new parameter.
_cli_profile_override: str | None = None


def set_profile_override(name: str | None) -> None:
    """Record the ``--profile`` value from the CLI for later resolution."""
    global _cli_profile_override
    _cli_profile_override = name


class ConfigError(Exception):
    """Raised when required env vars for the active environment are missing."""


@dataclass(frozen=True)
class EnvConfig:
    """Resolved credentials + base URL for one environment."""

    name: str  # Local label from conf file (e.g. "sandbox"). Cosmetic only.
    api_key: str
    business_id: str  # Canonical identity — checked against the directory pin.
    user_id: str
    base_url: str

    def auth_headers(self) -> dict[str, str]:
        return {
            "X-API-KEY": self.api_key,
            "X-BUSINESS-ID": self.business_id,
            "X-USER-ID": self.user_id,
        }


def load_env_config(
    env_name: str | None = None,
    dotenv_path: Path | None = None,
) -> EnvConfig:
    """Resolve the active environment's credentials.

    Selects a profile name (``env_name`` arg > ``--profile`` override >
    ``$KIZEN_PROFILE`` > directory pin > ``$KIZEN_ENV``), loads its credentials
    from the central store and enforces the directory pin's ``business_id``
    checksum before returning.
    """
    if dotenv_path is not None:
        load_dotenv(dotenv_path, override=False)
    else:
        load_dotenv(find_dotenv(usecwd=True), override=False)

    pin = profiles.load_pin()

    resolved = (
        env_name
        or _cli_profile_override
        or os.environ.get("KIZEN_PROFILE")
        or (pin.profile if pin else None)
        or os.environ.get("KIZEN_ENV")
    )
    if not resolved:
        raise ConfigError(
            "No environment specified. "
            "Run `kizen init` to configure one, or pass --profile <name>."
        )

    config = _load_profile(resolved)

    # Hard pin: whatever selected the profile, its identity must match what the
    # directory declared. Refuse loudly rather than act on the wrong env.
    if pin and pin.business_id and config.business_id != pin.business_id:
        raise ConfigError(
            f"Directory pinned to profile '{pin.profile}' "
            f"(business_id {pin.business_id}), but resolved profile "
            f"'{config.name}' has business_id {config.business_id}. Refusing.\n"
            f"To retarget this directory, edit {pin.path}."
        )

    return config


def _load_profile(name: str) -> EnvConfig:
    """Build an EnvConfig from the central credential store."""
    creds = profiles.get_profile(name)
    if creds is None:
        raise ConfigError(
            f"No profile named '{name}' in {profiles.credentials_path()}. "
            f"Run `kizen init --profile {name}` to configure it."
        )
    if not creds.api_key or not creds.business_id or not creds.user_id:
        raise ConfigError(
            f"Profile '{name}' in {profiles.credentials_path()} is missing "
            f"required fields. Run `kizen init --profile {name}` to re-enter them."
        )
    return EnvConfig(
        name=name.lower(),
        api_key=creds.api_key,
        business_id=creds.business_id,
        user_id=creds.user_id,
        base_url=creds.base_url,
    )
