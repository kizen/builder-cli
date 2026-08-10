"""Central credential store + per-directory profile pin.

Two concerns, deliberately separated:

* **Storage** — credentials for every Kizen environment live in one TOML file
  in the user's config dir (``$XDG_CONFIG_HOME/kizen/credentials.toml``,
  falling back to ``~/.config``), keyed by profile name. Secret, mode 0600,
  never committed.
* **Selection** — the *working directory* pins which profile it is allowed to
  use via a committed, non-secret ``.kizen/profile`` file that also records the
  expected ``business_id``.

Keeping storage central but selection positional (bound to the directory, not
to a mutable global "active profile") is what prevents an agent from silently
drifting onto the wrong environment: there is no ambient pointer to flip, and
the recorded ``business_id`` acts as a checksum on identity (enforced in
``config.load_env_config``).

Documentation is deliberately *not* a concern here — it ships inside the
package and is served by ``kizen docs show`` (see ``kizen_builder.docs``).
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

import tomli_w

DEFAULT_BASE_URL = "https://app.go.kizen.com"

# The pin is the only thing the CLI keeps in an env folder's .kizen/.
PIN_RELPATH = Path(".kizen") / "profile"


# ---------------------------------------------------------------------------
# Central credential store
# ---------------------------------------------------------------------------


def config_home() -> Path:
    """The kizen config directory, honoring ``$XDG_CONFIG_HOME``."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "kizen"


def credentials_path() -> Path:
    """Path to the central ``credentials.toml`` (may not exist yet)."""
    return config_home() / "credentials.toml"


@dataclass(frozen=True)
class ProfileCreds:
    """Credentials for one named profile, as stored centrally."""

    name: str
    api_key: str
    business_id: str
    user_id: str
    base_url: str


def _read_profiles_table(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    table = data.get("profiles", {})
    return table if isinstance(table, dict) else {}


def _creds_from_row(name: str, row: dict[str, str]) -> ProfileCreds:
    return ProfileCreds(
        name=name,
        api_key=row.get("api_key", ""),
        business_id=row.get("business_id", ""),
        user_id=row.get("user_id", ""),
        base_url=(row.get("base_url") or DEFAULT_BASE_URL).rstrip("/"),
    )


def get_profile(name: str, path: Path | None = None) -> ProfileCreds | None:
    """Return the named profile's credentials, or ``None`` if not stored."""
    table = _read_profiles_table(path or credentials_path())
    row = table.get(name)
    if not isinstance(row, dict):
        return None
    return _creds_from_row(name, row)


def list_profiles(path: Path | None = None) -> list[ProfileCreds]:
    """All stored profiles, sorted by name."""
    table = _read_profiles_table(path or credentials_path())
    return [_creds_from_row(name, row) for name, row in sorted(table.items())]


def write_profile(creds: ProfileCreds, path: Path | None = None) -> Path:
    """Upsert one profile into the central store (read-modify-write, 0600)."""
    target = path or credentials_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {}
    if target.exists():
        with target.open("rb") as fh:
            data = tomllib.load(fh)
    profiles = data.setdefault("profiles", {})
    profiles[creds.name] = {
        "api_key": creds.api_key,
        "business_id": creds.business_id,
        "user_id": creds.user_id,
        "base_url": creds.base_url,
    }

    with target.open("wb") as fh:
        tomli_w.dump(data, fh)
    os.chmod(target, 0o600)
    return target


# ---------------------------------------------------------------------------
# Per-directory pin
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Pin:
    """A directory's declared profile and its expected identity."""

    profile: str
    business_id: str | None
    path: Path  # the .kizen/profile file this came from


def find_pin(start: Path | None = None) -> Path | None:
    """Walk up from ``start`` (default cwd) looking for ``.kizen/profile``."""
    current = (start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        candidate = directory / PIN_RELPATH
        if candidate.is_file():
            return candidate
    return None


def load_pin(start: Path | None = None) -> Pin | None:
    """Load the directory pin, if any."""
    path = find_pin(start)
    if path is None:
        return None
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    profile = data.get("profile")
    if not profile:
        return None
    business_id = data.get("business_id") or None
    return Pin(profile=str(profile), business_id=business_id, path=path)


def write_pin(profile: str, business_id: str, directory: Path | None = None) -> Path:
    """Write ``<directory>/.kizen/profile`` pinning this dir to a profile."""
    base = directory or Path.cwd()
    path = base / PIN_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        tomli_w.dump({"profile": profile, "business_id": business_id}, fh)
    return path
