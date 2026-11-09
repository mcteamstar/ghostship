"""Legacy OAuth archives may only supply an absent default profile."""
import base64
from pathlib import Path
from unittest.mock import patch

import pytest

from transport.credentials import CredentialStore


def test_legacy_archive_is_default_only_and_never_overrides_store(tmp_path):
    legacy = Path(tmp_path) / "ga-codex-auth"
    legacy.write_bytes(b"synthetic-legacy")
    store = CredentialStore(tmp_path)
    assert base64.b64decode(store.get("codex")["payload"]) == b"synthetic-legacy"
    assert store.get("codex", "work") is None
    store.put("codex", "chatgpt", base64.b64encode(b"synthetic-profile"))
    assert base64.b64decode(store.get("codex")["payload"]) == b"synthetic-profile"
    assert legacy.read_bytes() == b"synthetic-legacy"


def test_corrupt_profile_does_not_fall_back_to_legacy(tmp_path):
    (tmp_path / "ga-codex-auth").write_bytes(b"synthetic-legacy")
    store = CredentialStore(tmp_path)
    profile = tmp_path / "credentials" / "codex" / "default.json"
    profile.parent.mkdir(parents=True)
    profile.write_text("invalid")
    assert store.get("codex") is None


def test_corrupt_default_never_deletes_legacy_flat_envelope(tmp_path):
    store = CredentialStore(tmp_path)
    flat = tmp_path / "credentials" / "codex.json"
    flat.parent.mkdir(parents=True)
    flat.write_text('{"backend":"codex","method":"chatgpt","payload":"YWJj"}')
    default = flat.parent / "codex" / "default.json"
    default.parent.mkdir()
    default.write_text("broken")
    assert store.get("codex") is None
    assert flat.exists()


def test_failed_flat_migration_preserves_source_and_named_profile(tmp_path):
    store = CredentialStore(tmp_path)
    store.put("codex", "api-key", "synthetic-named-key", profile="work")
    flat = tmp_path / "credentials" / "codex.json"
    flat.write_text('{"backend":"codex","method":"chatgpt","payload":"YWJj"}')
    with patch("transport.credentials.os.replace", side_effect=OSError("synthetic failure")):
        with pytest.raises(OSError):
            store.get("codex")
    assert flat.exists()
    assert store.get("codex", "work")["payload"] == b"synthetic-named-key"
    assert store.get("codex")["payload"] == b"abc"
    assert store.get("codex")["payload"] == b"abc"
