"""Exercise actual crew setup against synthetic profile stores and Podman."""
import base64
import io
import tarfile
from unittest.mock import MagicMock

import pytest

from transport import academy, launcher, lifecycle
from transport.credentials import CredentialStore


def _archive(marker):
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode="w") as archive:
        item = tarfile.TarInfo("auth.json")
        item.size = len(marker)
        archive.addfile(item, io.BytesIO(marker))
    return result.getvalue()


@pytest.mark.parametrize(("backend", "method", "inject_name"), [
    ("codex", "chatgpt", "_inject_codex_auth"),
    ("claude", "oauth", "_inject_claude_auth"),
])
def test_finish_setup_injects_the_selected_profile(tmp_path, monkeypatch, backend, method, inject_name):
    store = CredentialStore(tmp_path)
    first, second = _archive(b"fixture-one"), _archive(b"fixture-two")
    store.put(backend, method, base64.b64encode(first), profile="one")
    store.put(backend, method, base64.b64encode(second), profile="two")
    monkeypatch.setattr(lifecycle, "_cred_store", store)
    inject = MagicMock()
    monkeypatch.setattr(lifecycle, inject_name, inject)
    for name, result in {
        "_wait_gateway": True, "_inject_policy": 1,
        "_mint_cookie": "gateway-cookie", "_mint_internal_cookie": None,
        "_prewarm_crew": {"status": "warmed"}, "_secret_identifier": "id",
    }.items():
        monkeypatch.setattr(lifecycle, name, MagicMock(return_value=result))
    for name in ("_patch_crew_config", "_seed_openspec_store", "_patch_models", "_enroll_crew_members"):
        monkeypatch.setattr(lifecycle, name, MagicMock())
    loader = MagicMock()
    loader.copy_all.return_value = {"agents": []}
    monkeypatch.setattr(academy, "AcademyLoader", MagicMock(return_value=loader))
    registry = MagicMock()
    registry.__enter__.return_value = registry
    monkeypatch.setattr(launcher, "registry", registry)
    podman = MagicMock()
    podman.container_exec.return_value = "ready"
    podman.container_inspect.return_value = {}
    service = launcher.CrewLauncher(registry=registry, podman=podman, cfg=lifecycle.cfg)

    for profile, expected in (("one", first), ("two", second)):
        result = service.finish_setup(
            podman, f"crew-{profile}", f"gs-{profile}", "workspace", "home",
            "", admiral_secret="test", backend=backend, acp_profile=profile,
            credential=store.get(backend, profile),
        )
        assert result["acp_profile"] == profile
        assert inject.call_args.args == (podman, f"gs-{profile}", expected)

    # A pre-isolation archive written by the last named login must never be
    # served as the default identity while named profiles exist.
    (tmp_path / f"ga-{backend}-auth").write_bytes(first)
    assert store.get(backend, "default") is None
    with pytest.raises(RuntimeError, match="No usable credential"):
        service.finish_setup(
            podman, "crew-default", "gs-default", "workspace", "home", "",
            admiral_secret="test", backend=backend, acp_profile="default",
            credential=None,
        )

    # With no profile envelopes at all, the legacy archive still supplies the
    # implicit default for installs upgraded from the single-archive layout.
    legacy_root = tmp_path / "legacy-only"
    legacy_root.mkdir()
    (legacy_root / f"ga-{backend}-auth").write_bytes(first)
    legacy_store = CredentialStore(legacy_root)
    monkeypatch.setattr(lifecycle, "_cred_store", legacy_store)
    result = service.finish_setup(
        podman, "crew-default", "gs-default", "workspace", "home", "",
        admiral_secret="test", backend=backend, acp_profile="default",
        credential=legacy_store.get(backend, "default"),
    )
    assert result["acp_profile"] == "default"
    assert inject.call_args.args == (podman, "gs-default", first)
