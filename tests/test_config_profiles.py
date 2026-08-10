"""Profile resolution: precedence ladder, business_id checksum, legacy fallback.

These exercise the anti-drift guarantees in ``config.load_env_config`` and the
IO in ``profiles``. The autouse ``fake_env`` fixture points XDG_CONFIG_HOME at
an empty temp dir and disables the directory pin, so each test builds exactly
the state it needs.
"""

from __future__ import annotations

import pytest

from kizen_builder import config, profiles
from kizen_builder.config import ConfigError, load_env_config

# Captured before the autouse fixture patches it, so pin-IO tests can restore
# the real directory walk.
_REAL_FIND_PIN = profiles.find_pin


@pytest.fixture(autouse=True)
def _reset_override():
    """Keep the module-global CLI override from leaking between tests."""
    config.set_profile_override(None)
    yield
    config.set_profile_override(None)


def _store(name: str, business_id: str) -> None:
    profiles.write_profile(
        profiles.ProfileCreds(
            name=name,
            api_key=f"key-{name}",
            business_id=business_id,
            user_id=f"user-{name}",
            base_url="https://app.go.kizen.com",
        )
    )


def _pin(monkeypatch, profile: str, business_id: str | None) -> None:
    pin = profiles.Pin(
        profile=profile, business_id=business_id, path="/x/.kizen/profile"
    )
    monkeypatch.setattr(profiles, "load_pin", lambda start=None: pin)


# --- credential store IO ----------------------------------------------------


def test_write_then_read_profile_roundtrips():
    _store("alpha", "AAAA")
    got = profiles.get_profile("alpha")
    assert got is not None
    assert got.business_id == "AAAA"
    assert got.api_key == "key-alpha"


def test_write_profile_is_upsert_not_clobber():
    _store("alpha", "AAAA")
    _store("beta", "BBBB")
    names = [p.name for p in profiles.list_profiles()]
    assert names == ["alpha", "beta"]


def test_write_pin_then_load_pin_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "find_pin", _REAL_FIND_PIN)  # real walk for this test
    path = profiles.write_pin("alpha", "AAAA", tmp_path)
    loaded = profiles.load_pin(tmp_path)
    assert loaded is not None
    assert loaded.profile == "alpha"
    assert loaded.business_id == "AAAA"
    assert loaded.path == path


# --- resolution precedence --------------------------------------------------


def test_kizen_env_selects_profile(monkeypatch):
    _store("alpha", "AAAA")
    monkeypatch.setenv("KIZEN_ENV", "alpha")
    assert load_env_config().business_id == "AAAA"


def test_kizen_profile_beats_kizen_env(monkeypatch):
    _store("alpha", "AAAA")
    _store("beta", "BBBB")
    monkeypatch.setenv("KIZEN_ENV", "alpha")
    monkeypatch.setenv("KIZEN_PROFILE", "beta")
    assert load_env_config().name == "beta"


def test_cli_override_beats_kizen_profile(monkeypatch):
    _store("alpha", "AAAA")
    _store("beta", "BBBB")
    monkeypatch.setenv("KIZEN_PROFILE", "beta")
    config.set_profile_override("alpha")
    assert load_env_config().name == "alpha"


def test_pin_beats_kizen_env(monkeypatch):
    _store("alpha", "AAAA")
    _store("beta", "BBBB")
    monkeypatch.setenv("KIZEN_ENV", "alpha")
    _pin(monkeypatch, "beta", "BBBB")
    assert load_env_config().name == "beta"


# --- hard-pin checksum ------------------------------------------------------


def test_checksum_refuses_pin_profile_business_id_mismatch(monkeypatch):
    _store("alpha", "AAAA")
    _pin(monkeypatch, "alpha", "ZZZZ")  # pin claims a different identity
    with pytest.raises(ConfigError, match="Refusing"):
        load_env_config()


def test_checksum_refuses_override_into_pinned_directory(monkeypatch):
    # The agent-drift case: directory pinned to alpha, command forces beta.
    _store("alpha", "AAAA")
    _store("beta", "BBBB")
    _pin(monkeypatch, "alpha", "AAAA")
    config.set_profile_override("beta")
    with pytest.raises(ConfigError, match="Refusing"):
        load_env_config()


def test_checksum_passes_when_identity_matches(monkeypatch):
    _store("alpha", "AAAA")
    _pin(monkeypatch, "alpha", "AAAA")
    assert load_env_config().business_id == "AAAA"


# --- legacy fallback --------------------------------------------------------


def test_legacy_env_used_when_no_stored_profile(monkeypatch):
    # No profile in the store; fake_env's API_KEY/BUSINESS_ID env vars stand in.
    from tests.conftest import FAKE_BUSINESS_ID

    monkeypatch.setenv("KIZEN_ENV", "testenv")
    cfg = load_env_config()
    assert cfg.name == "testenv"
    assert cfg.business_id == FAKE_BUSINESS_ID


def test_no_env_at_all_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("KIZEN_ENV", raising=False)
    monkeypatch.delenv("KIZEN_PROFILE", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)
    # Explicit path bypasses find_dotenv so the repo's own .env can't leak in.
    with pytest.raises(ConfigError, match="No environment specified"):
        load_env_config(dotenv_path=tmp_path / "nonexistent.env")


# Docs are no longer materialized into env folders — they ship inside the
# package and are served by `kizen docs show`. See tests/test_docs.py.
