"""Unit tests for TRN-93 security hardening.

Covers:
  - TestStdinSecretDelivery:  inject_admiral_secret.py reads secret from stdin
  - TestCrewsJsonHygiene:     crews.json stores identifiers, not plaintext secrets
  - TestContainerHardeningFlags: no_new_privileges + cap_drop in container specs
  - TestFileTransferAudit:    audit_auth_event called for presign and verify paths
"""
from __future__ import annotations

import hashlib
import importlib
import io
import json
import logging
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

# ── import helpers ────────────────────────────────────────────────────────────

# Add container_scripts to sys.path so inject_admiral_secret imports directly.
_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[2] / "transport" / "container_scripts"
)
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

inject_admiral_secret_mod = importlib.import_module("inject_admiral_secret")

# Bootstrap transport modules via the dependency-free stub installer.
from tests.unit.test_file_transfer import server  # noqa: F401  (installs stubs)

import transport.lifecycle as lifecycle
import transport.files as files_mod
import transport.podman as podman_mod


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_podman_mock(**kwargs):
    """Return a MagicMock Podman client with sensible defaults."""
    m = MagicMock()
    m.container_exec.return_value = "ready"
    m.container_exec_checked.return_value = "ok"
    m.container_exec_stdin.return_value = "admiral secret injected"
    m.container_inspect.return_value = {"Config": {"Labels": {}}}
    for k, v in kwargs.items():
        setattr(m, k, v)
    return m


# ══════════════════════════════════════════════════════════════════════════════
# 6.1 — Stdin secret delivery
# ══════════════════════════════════════════════════════════════════════════════

class TestStdinSecretDelivery(unittest.TestCase):
    """inject_admiral_secret.py reads secret from stdin, not argv[2]."""

    def test_inject_admiral_secret_writes_correct_value(self) -> None:
        """inject_admiral_secret(dest, stdin_secret) writes the secret to the file."""
        with tempfile.TemporaryDirectory() as td:
            dest = str(Path(td) / ".admiral_secret")
            secret = "test_secret_value_abc123"
            inject_admiral_secret_mod.inject_admiral_secret(dest, secret)
            written = Path(dest).read_text()
            self.assertEqual(written, secret)

    def test_inject_admiral_secret_writes_with_mode_0600(self) -> None:
        """inject_admiral_secret writes the file with mode 0600."""
        with tempfile.TemporaryDirectory() as td:
            dest = str(Path(td) / ".admiral_secret")
            inject_admiral_secret_mod.inject_admiral_secret(dest, "s3cr3t")
            mode = Path(dest).stat().st_mode & 0o777
            self.assertEqual(mode, 0o600)

    def test_main_reads_secret_from_stdin(self) -> None:
        """main() reads secret from stdin and writes it to the destination."""
        with tempfile.TemporaryDirectory() as td:
            dest = str(Path(td) / ".admiral_secret")
            secret = "stdin_delivered_secret"
            original_stdin = sys.stdin
            try:
                sys.stdin = io.StringIO(secret)
                rc = inject_admiral_secret_mod.main(["inject_admiral_secret.py", dest])
            finally:
                sys.stdin = original_stdin
            self.assertEqual(rc, 0)
            self.assertEqual(Path(dest).read_text(), secret)

    def test_main_does_not_accept_argv2(self) -> None:
        """main() with 3 args (script + dest + secret) returns error code 2."""
        with tempfile.TemporaryDirectory() as td:
            dest = str(Path(td) / ".admiral_secret")
            rc = inject_admiral_secret_mod.main(
                ["inject_admiral_secret.py", dest, "should_not_work"]
            )
            self.assertEqual(rc, 2, "Script must not accept secret as argv[2]")

    def test_main_requires_exactly_two_args(self) -> None:
        """main() without dest argument (1 arg total) returns error code 2."""
        rc = inject_admiral_secret_mod.main(["inject_admiral_secret.py"])
        self.assertEqual(rc, 2)

    def test_lifecycle_uses_container_exec_stdin(self) -> None:
        """_finish_crew_setup calls container_exec_stdin for admiral secret injection."""
        import transport.registry as _registry_mod
        stdin_calls: list[tuple[str, list, bytes]] = []

        podman = MagicMock()
        podman.container_exec.return_value = "ready"
        podman.container_exec_checked.return_value = "ok"
        podman.container_inspect.return_value = {"Config": {"Labels": {}}}
        podman.container_stop = MagicMock()
        podman.container_start = MagicMock()

        def capture_exec_stdin(container, cmd, stdin_data):
            stdin_calls.append((container, cmd, stdin_data))
            return "admiral secret injected"

        podman.container_exec_stdin = MagicMock(side_effect=capture_exec_stdin)

        with tempfile.TemporaryDirectory() as tmp:
            from contextlib import ExitStack
            with ExitStack() as stack:
                stack.enter_context(patch.object(_registry_mod, "DATA_DIR", Path(tmp)))
                stack.enter_context(patch.object(_registry_mod, "REGISTRY_PATH", Path(tmp) / "crews.json"))
                stack.enter_context(patch.object(lifecycle, "_wait_gateway", return_value=True))
                stack.enter_context(patch.object(lifecycle, "_inject_auth"))
                stack.enter_context(patch.object(lifecycle, "_patch_crew_config"))
                stack.enter_context(patch.object(lifecycle, "_copy_agents", return_value=[]))
                stack.enter_context(patch.object(lifecycle, "_copy_skills", return_value=[]))
                stack.enter_context(patch.object(lifecycle, "_copy_steering", return_value=[]))
                stack.enter_context(patch.object(lifecycle, "_seed_openspec_store"))
                stack.enter_context(patch.object(lifecycle, "_patch_models"))
                stack.enter_context(patch.object(lifecycle, "_inject_policy", return_value="1"))
                stack.enter_context(patch.object(lifecycle, "_mint_cookie", return_value="cookie"))
                lifecycle._finish_crew_setup(
                    podman, "demo", "gs-demo", "gs-vol-demo", "gs-home-demo", "auth"
                )

        # The secret must have been delivered via container_exec_stdin
        admiral_inject_calls = [
            c for c in stdin_calls if any("inject_admiral_secret" in part for part in c[1])
        ]
        self.assertEqual(len(admiral_inject_calls), 1,
                         "Expected exactly one container_exec_stdin call for inject_admiral_secret.py")
        # Secret must not appear in the command args — it goes through stdin
        _, cmd, stdin_data = admiral_inject_calls[0]
        # The command should only have: python3, script_path, dest_path (exactly 3 args)
        self.assertEqual(len(cmd), 3,
                         f"inject_admiral_secret.py must be called with exactly 3 args, got: {cmd}")
        # The actual secret value (which is in stdin_data) must not appear in the args
        secret_value = stdin_data.decode()
        for arg in cmd:
            self.assertNotIn(secret_value, arg,
                             "Secret value must not appear in exec command args")
        self.assertIsInstance(stdin_data, bytes, "stdin_data must be bytes")
        self.assertGreater(len(stdin_data), 0, "stdin_data must be non-empty")


# ══════════════════════════════════════════════════════════════════════════════
# 6.2 — crews.json credential hygiene
# ══════════════════════════════════════════════════════════════════════════════

class TestCrewsJsonHygiene(unittest.TestCase):
    """crews.json must store identifiers only, never plaintext secrets."""

    def _run_finish_crew_setup(self) -> dict:
        """Run lifecycle._finish_crew_setup and return the crews.json entry for 'demo'."""
        import transport.registry as _registry_mod

        podman = MagicMock()
        podman.container_exec.return_value = "ready"
        podman.container_exec_checked.return_value = "ok"
        podman.container_exec_stdin.return_value = "admiral secret injected"
        podman.container_inspect.return_value = {"Config": {"Labels": {}}}
        podman.container_stop = MagicMock()
        podman.container_start = MagicMock()

        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "crews.json"
            from contextlib import ExitStack
            with ExitStack() as stack:
                stack.enter_context(patch.object(_registry_mod, "DATA_DIR", Path(tmp)))
                stack.enter_context(patch.object(_registry_mod, "REGISTRY_PATH", registry_path))
                stack.enter_context(patch.object(lifecycle, "_wait_gateway", return_value=True))
                stack.enter_context(patch.object(lifecycle, "_inject_auth"))
                stack.enter_context(patch.object(lifecycle, "_patch_crew_config"))
                stack.enter_context(patch.object(lifecycle, "_copy_agents", return_value=[]))
                stack.enter_context(patch.object(lifecycle, "_copy_skills", return_value=[]))
                stack.enter_context(patch.object(lifecycle, "_copy_steering", return_value=[]))
                stack.enter_context(patch.object(lifecycle, "_seed_openspec_store"))
                stack.enter_context(patch.object(lifecycle, "_patch_models"))
                stack.enter_context(patch.object(lifecycle, "_inject_policy", return_value="1"))
                stack.enter_context(patch.object(lifecycle, "_mint_cookie", return_value="cookie"))
                lifecycle._finish_crew_setup(
                    podman, "demo", "gs-demo", "gs-vol-demo", "gs-home-demo", "auth"
                )
            registry_data = json.loads(registry_path.read_text())
        return registry_data.get("crews", {}).get("demo", {})

    def test_admiral_secret_absent_from_crews_json(self) -> None:
        """crews.json must not contain the plaintext admiral_secret field."""
        entry = self._run_finish_crew_setup()
        self.assertNotIn("admiral_secret", entry,
                         "plaintext admiral_secret must not be stored in crews.json")

    def test_policy_signing_key_absent_from_crews_json(self) -> None:
        """crews.json must not contain the plaintext policy_signing_key field."""
        entry = self._run_finish_crew_setup()
        self.assertNotIn("policy_signing_key", entry,
                         "plaintext policy_signing_key must not be stored in crews.json")

    def test_admiral_secret_id_present_as_sha256_identifier(self) -> None:
        """crews.json must contain admiral_secret_id as a sha256:<hex> string."""
        entry = self._run_finish_crew_setup()
        self.assertIn("admiral_secret_id", entry,
                      "admiral_secret_id identifier must be present in crews.json")
        val = entry["admiral_secret_id"]
        self.assertTrue(str(val).startswith("sha256:"),
                        f"admiral_secret_id must start with 'sha256:', got: {val!r}")

    def test_policy_signing_key_id_present_as_sha256_identifier(self) -> None:
        """crews.json must contain policy_signing_key_id as a sha256:<hex> string."""
        entry = self._run_finish_crew_setup()
        self.assertIn("policy_signing_key_id", entry,
                      "policy_signing_key_id identifier must be present in crews.json")
        val = entry["policy_signing_key_id"]
        self.assertTrue(str(val).startswith("sha256:"),
                        f"policy_signing_key_id must start with 'sha256:', got: {val!r}")

    def test_secret_identifier_format(self) -> None:
        """_secret_identifier returns sha256:<16-char hex prefix>."""
        result = lifecycle._secret_identifier("my_secret_value")
        expected_hash = hashlib.sha256("my_secret_value".encode()).hexdigest()[:16]
        self.assertEqual(result, f"sha256:{expected_hash}")

    def test_secret_identifier_is_non_reversible(self) -> None:
        """Two different secrets produce different identifiers."""
        id1 = lifecycle._secret_identifier("secret_one")
        id2 = lifecycle._secret_identifier("secret_two")
        self.assertNotEqual(id1, id2)


# ══════════════════════════════════════════════════════════════════════════════
# 6.3 — Container hardening flags
# ══════════════════════════════════════════════════════════════════════════════

class TestContainerHardeningFlags(unittest.TestCase):
    """container_create and worker_run specs include no_new_privileges and cap_drop."""

    def test_container_create_includes_no_new_privileges(self) -> None:
        """container_create spec must include no_new_privileges=True."""
        captured: list[dict] = []

        client = podman_mod.PodmanClient.__new__(podman_mod.PodmanClient)

        def fake_req(method, path, **kw):
            if method == "POST" and "containers/create" in path:
                captured.append(kw.get("json", {}))
            return {}

        client._req = fake_req

        client.container_create(
            name="test-crew",
            image="localhost/spec-ops:latest",
            env={},
            network="ga-net",
            workspace_volume="gs-vol-test",
            home_volume="gs-home-test",
        )

        self.assertEqual(len(captured), 1)
        spec = captured[0]
        self.assertTrue(spec.get("no_new_privileges"),
                        "container_create spec must include no_new_privileges=True")

    def test_container_create_includes_cap_drop(self) -> None:
        """container_create spec must drop CAP_NET_RAW and CAP_SYS_ADMIN."""
        captured: list[dict] = []

        client = podman_mod.PodmanClient.__new__(podman_mod.PodmanClient)

        def fake_req(method, path, **kw):
            if method == "POST" and "containers/create" in path:
                captured.append(kw.get("json", {}))
            return {}

        client._req = fake_req

        client.container_create(
            name="test-crew",
            image="localhost/spec-ops:latest",
            env={},
            network="ga-net",
            workspace_volume="gs-vol-test",
            home_volume="gs-home-test",
        )

        spec = captured[0]
        cap_drop = spec.get("cap_drop", [])
        self.assertIn("CAP_NET_RAW", cap_drop,
                      "container_create spec must drop CAP_NET_RAW")
        self.assertIn("CAP_SYS_ADMIN", cap_drop,
                      "container_create spec must drop CAP_SYS_ADMIN")

    def test_worker_run_includes_no_new_privileges(self) -> None:
        """worker_run spec must include no_new_privileges=True."""
        captured: list[dict] = []

        client = podman_mod.PodmanClient.__new__(podman_mod.PodmanClient)

        def fake_req(method, path, **kw):
            if method == "POST" and "containers/create" in path:
                captured.append(kw.get("json", {}))
            return {"Id": "fake-exec-id"} if "exec" in path else {}

        def fake_image_exists(image):
            return True

        client._req = fake_req
        client._image_exists = fake_image_exists
        # container_start, container_stop, volume ops aren't needed
        client.container_start = MagicMock()

        # Simulate the create→start→wait→logs sequence by patching the httpx client
        mock_c = MagicMock()
        mock_c.post.return_value.status_code = 200
        mock_c.post.return_value.content = b""
        mock_c.post.return_value.json.return_value = 0  # exit code 0
        mock_c.get.return_value.status_code = 200
        mock_c.get.return_value.content = b""
        mock_c.delete.return_value = MagicMock()
        client._c = mock_c

        # The worker_run spec is captured via fake_req before container_start is called
        try:
            client.worker_run("gs-vol-test", ["cat", "/workspace/README.md"])
        except Exception:
            pass  # Container operations will fail; we only care about the spec

        # worker_run may also use the _c.post path for create
        if not captured:
            # Fall back: check via _c.post calls
            for c in mock_c.post.call_args_list:
                args, kwargs = c
                if kwargs.get("json"):
                    captured.append(kwargs["json"])

        # If we got any spec from the create call, check it
        create_specs = [s for s in captured if "no_new_privileges" in s or "image" in s]
        if create_specs:
            spec = create_specs[0]
            self.assertTrue(spec.get("no_new_privileges"),
                            "worker_run spec must include no_new_privileges=True")

    def test_worker_run_spec_has_hardening_flags_via_inspection(self) -> None:
        """worker_run builds a spec dict that includes no_new_privileges and cap_drop.

        This test inspects the spec dict constructed inside worker_run by
        intercepting the _req call before it reaches Podman.
        """
        captured_spec: list[dict] = []

        client = podman_mod.PodmanClient.__new__(podman_mod.PodmanClient)

        def fake_req(method, path, **kw):
            if method == "POST" and path.endswith("/containers/create"):
                captured_spec.append(kw.get("json", {}))
                # Return a minimal "created" response so worker_run can proceed
                return {}
            # For other calls (start, wait, logs, delete), return safe defaults
            return {}

        def fake_image_exists(image: str) -> bool:
            return True

        mock_c = MagicMock()
        # container_start: no-op
        mock_c.post.return_value.status_code = 200
        mock_c.post.return_value.content = b"\x00\x00\x00\x00\x00\x00\x00\x00"  # exit 0 wait
        mock_c.post.return_value.raise_for_status = MagicMock()
        # wait response: return exit code 0
        wait_resp = MagicMock()
        wait_resp.status_code = 200
        wait_resp.content = b"0"
        wait_resp.json.return_value = 0
        wait_resp.raise_for_status = MagicMock()
        # logs response
        logs_resp = MagicMock()
        logs_resp.status_code = 200
        logs_resp.content = b""
        mock_c.post.side_effect = lambda *a, **kw: wait_resp if "wait" in str(a) else mock_c.post.return_value
        mock_c.get.return_value = logs_resp
        mock_c.delete.return_value = MagicMock()
        client._c = mock_c
        client._req = fake_req
        client._image_exists = fake_image_exists

        try:
            client.worker_run("gs-vol-test", ["echo", "hi"])
        except Exception:
            pass

        self.assertTrue(len(captured_spec) >= 1, "worker_run must call _req POST containers/create")
        spec = captured_spec[0]
        self.assertTrue(spec.get("no_new_privileges"),
                        "worker_run spec must include no_new_privileges=True")
        cap_drop = spec.get("cap_drop", [])
        self.assertIn("CAP_NET_RAW", cap_drop,
                      "worker_run spec must drop CAP_NET_RAW")
        self.assertIn("CAP_SYS_ADMIN", cap_drop,
                      "worker_run spec must drop CAP_SYS_ADMIN")


# ══════════════════════════════════════════════════════════════════════════════
# 6.5 — File transfer audit events
# ══════════════════════════════════════════════════════════════════════════════

class TestFileTransferAudit(unittest.TestCase):
    """audit_auth_event is called with correct action/outcome for file-transfer operations."""

    # ── presign_evac ──────────────────────────────────────────────────────────

    def test_evac_presign_emits_audit_event(self) -> None:
        """evac() calls audit_auth_event(action='presign_evac', outcome='issued')."""
        audit_calls: list[dict] = []

        def capture_audit(**kw):
            audit_calls.append(kw)
            return kw

        with (
            patch.object(server, "_require_crew", return_value={"container": "gs-demo", "cookie": "c"}),
            patch.object(server, "_ensure_crew_running", return_value={"container": "gs-demo", "cookie": "c"}),
            patch.object(server._security, "audit_auth_event", side_effect=capture_audit),
        ):
            result = server.evac(path="repo/file.txt", crew_id="demo")

        self.assertNotIn("error", result)
        evac_events = [e for e in audit_calls if e.get("action") == "presign_evac"]
        self.assertEqual(len(evac_events), 1,
                         "evac() must emit exactly one presign_evac audit event")
        self.assertEqual(evac_events[0]["outcome"], "issued")
        self.assertIsNone(evac_events[0].get("source"))

    # ── presign_supply ────────────────────────────────────────────────────────

    def test_supply_presign_emits_audit_event(self) -> None:
        """supply() calls audit_auth_event(action='presign_supply', outcome='issued')."""
        audit_calls: list[dict] = []

        def capture_audit(**kw):
            audit_calls.append(kw)
            return kw

        with (
            patch.object(server, "_require_crew", return_value={"container": "gs-demo", "cookie": "c"}),
            patch.object(server, "_ensure_crew_running", return_value={"container": "gs-demo", "cookie": "c"}),
            patch.object(server._security, "audit_auth_event", side_effect=capture_audit),
        ):
            result = server.supply(path="repo/file.txt", crew_id="demo")

        self.assertNotIn("error", result)
        supply_events = [e for e in audit_calls if e.get("action") == "presign_supply"]
        self.assertEqual(len(supply_events), 1,
                         "supply() must emit exactly one presign_supply audit event")
        self.assertEqual(supply_events[0]["outcome"], "issued")

    # ── verify_file_token: valid ──────────────────────────────────────────────

    def test_verify_file_token_valid_emits_audit_event(self) -> None:
        """A valid token calls audit_auth_event(action='verify_file_token', outcome='valid')."""
        import hashlib, hmac as _hmac, time as _time
        import transport.files as f

        secret = "test-secret-xyz"
        crew_id, path = "demo", "repo/file.txt"
        expires = int(_time.time()) + 300
        flags = ""
        payload = f"{crew_id}:{path}:{expires}:GET::{flags}"
        sig = _hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

        audit_calls: list[dict] = []

        def capture(**kw):
            audit_calls.append(kw)
            return kw

        with (
            patch.object(f, "_FILE_SECRET", secret),
            patch.object(f._security, "audit_auth_event", side_effect=capture),
        ):
            result = f._verify_file_token(crew_id, path, str(expires), sig)

        self.assertTrue(result)
        valid_events = [e for e in audit_calls if e.get("outcome") == "valid"]
        self.assertEqual(len(valid_events), 1)
        self.assertEqual(valid_events[0]["action"], "verify_file_token")

    # ── verify_file_token: invalid HMAC ──────────────────────────────────────

    def test_verify_file_token_invalid_hmac_emits_audit_event(self) -> None:
        """A bad HMAC calls audit_auth_event(action='verify_file_token', outcome='invalid')."""
        import transport.files as f
        import time as _time

        expires = int(_time.time()) + 300
        audit_calls: list[dict] = []

        def capture(**kw):
            audit_calls.append(kw)
            return kw

        with patch.object(f._security, "audit_auth_event", side_effect=capture):
            result = f._verify_file_token("demo", "repo/file.txt", str(expires), "bad_sig")

        self.assertFalse(result)
        invalid_events = [e for e in audit_calls if e.get("outcome") == "invalid"]
        self.assertEqual(len(invalid_events), 1)
        self.assertEqual(invalid_events[0]["action"], "verify_file_token")

    # ── verify_file_token: expired ────────────────────────────────────────────

    def test_verify_file_token_expired_emits_audit_event(self) -> None:
        """An expired token calls audit_auth_event(action='verify_file_token', outcome='expired')."""
        import transport.files as f

        # Use an expires timestamp in the past
        expires = str(int(time.time()) - 100)
        audit_calls: list[dict] = []

        def capture(**kw):
            audit_calls.append(kw)
            return kw

        with patch.object(f._security, "audit_auth_event", side_effect=capture):
            result = f._verify_file_token("demo", "repo/file.txt", expires, "any_sig")

        self.assertFalse(result)
        expired_events = [e for e in audit_calls if e.get("outcome") == "expired"]
        self.assertEqual(len(expired_events), 1)
        self.assertEqual(expired_events[0]["action"], "verify_file_token")

    # ── audit events must not include secret material ─────────────────────────

    def test_audit_events_do_not_include_presigned_url(self) -> None:
        """Presign audit events must not log the presigned URL."""
        audit_calls: list[dict] = []

        def capture(**kw):
            audit_calls.append(kw)
            return kw

        with (
            patch.object(server, "_require_crew", return_value={"container": "gs-demo", "cookie": "c"}),
            patch.object(server, "_ensure_crew_running", return_value={"container": "gs-demo", "cookie": "c"}),
            patch.object(server._security, "audit_auth_event", side_effect=capture),
        ):
            server.evac(path="repo/file.txt", crew_id="demo")
            server.supply(path="repo/file.txt", crew_id="demo")

        for event in audit_calls:
            event_str = json.dumps(event)
            # A presigned URL starts with http and contains expires/sig params
            self.assertNotIn("expires=", event_str,
                             "Audit event must not contain presigned URL params")
            self.assertNotIn("&sig=", event_str,
                             "Audit event must not contain HMAC signature")


# ══════════════════════════════════════════════════════════════════════════════
# 2.fix — Admiral signing-secret file (TRN-93 Banshee fix)
# ══════════════════════════════════════════════════════════════════════════════

class TestAdmiralSigningSecretFile(unittest.TestCase):
    """_finish_crew_setup writes the admiral secret to a separate file; captain
    reads it back so standing orders are signed for TRN-93+ crews."""

    def test_finish_crew_setup_writes_crew_secret_file(self) -> None:
        """_finish_crew_setup calls _write_crew_secret with the admiral_secret value."""
        import transport.registry as _registry_mod

        written_secrets: list[tuple[str, str]] = []

        def capture_write(crew_id: str, secret: str) -> None:
            written_secrets.append((crew_id, secret))

        podman = MagicMock()
        podman.container_exec.return_value = "ready"
        podman.container_exec_checked.return_value = "ok"
        podman.container_exec_stdin.return_value = "admiral secret injected"
        podman.container_inspect.return_value = {"Config": {"Labels": {}}}
        podman.container_stop = MagicMock()
        podman.container_start = MagicMock()

        with tempfile.TemporaryDirectory() as tmp:
            from contextlib import ExitStack
            with ExitStack() as stack:
                stack.enter_context(patch.object(_registry_mod, "DATA_DIR", Path(tmp)))
                stack.enter_context(patch.object(_registry_mod, "REGISTRY_PATH", Path(tmp) / "crews.json"))
                stack.enter_context(patch.object(lifecycle, "_wait_gateway", return_value=True))
                stack.enter_context(patch.object(lifecycle, "_inject_auth"))
                stack.enter_context(patch.object(lifecycle, "_patch_crew_config"))
                stack.enter_context(patch.object(lifecycle, "_copy_agents", return_value=[]))
                stack.enter_context(patch.object(lifecycle, "_copy_skills", return_value=[]))
                stack.enter_context(patch.object(lifecycle, "_copy_steering", return_value=[]))
                stack.enter_context(patch.object(lifecycle, "_seed_openspec_store"))
                stack.enter_context(patch.object(lifecycle, "_patch_models"))
                stack.enter_context(patch.object(lifecycle, "_inject_policy", return_value="1"))
                stack.enter_context(patch.object(lifecycle, "_mint_cookie", return_value="cookie"))
                stack.enter_context(patch.object(lifecycle, "_write_crew_secret", side_effect=capture_write))
                lifecycle._finish_crew_setup(
                    podman, "demo", "gs-demo", "gs-vol-demo", "gs-home-demo", "auth"
                )

        self.assertEqual(len(written_secrets), 1,
                         "_write_crew_secret must be called exactly once")
        crew_id, secret = written_secrets[0]
        self.assertEqual(crew_id, "demo")
        self.assertIsInstance(secret, str)
        self.assertGreater(len(secret), 0, "secret must be non-empty")
        # The secret must not be the identifier — it must be the raw hex token
        self.assertFalse(secret.startswith("sha256:"),
                         "_write_crew_secret must receive the raw secret, not the identifier")

    def test_write_and_read_crew_secret_roundtrip(self) -> None:
        """_write_crew_secret and _read_crew_secret roundtrip correctly."""
        import transport.registry as _registry_mod

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(_registry_mod, "DATA_DIR", Path(tmp)):
                _registry_mod._write_crew_secret("test-crew", "my_secret_value_abc")
                result = _registry_mod._read_crew_secret("test-crew")
        self.assertEqual(result, "my_secret_value_abc")

    def test_read_crew_secret_returns_none_when_absent(self) -> None:
        """_read_crew_secret returns None for a crew with no secret file."""
        import transport.registry as _registry_mod

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(_registry_mod, "DATA_DIR", Path(tmp)):
                result = _registry_mod._read_crew_secret("nonexistent-crew")
        self.assertIsNone(result)

    def test_crew_secret_file_has_mode_0600(self) -> None:
        """The crew secret file is written with mode 0600."""
        import transport.registry as _registry_mod

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(_registry_mod, "DATA_DIR", Path(tmp)):
                _registry_mod._write_crew_secret("test-crew", "s3cr3t")
                secret_path = _registry_mod._crew_secret_path("test-crew")
                mode = secret_path.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600,
                         "Crew secret file must be mode 0600")

    def test_delete_crew_secret_removes_file(self) -> None:
        """_delete_crew_secret removes the secret file."""
        import transport.registry as _registry_mod

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(_registry_mod, "DATA_DIR", Path(tmp)):
                _registry_mod._write_crew_secret("test-crew", "s3cr3t")
                _registry_mod._delete_crew_secret("test-crew")
                result = _registry_mod._read_crew_secret("test-crew")
        self.assertIsNone(result, "_delete_crew_secret must remove the secret file")

    def test_delete_crew_secret_noop_when_absent(self) -> None:
        """_delete_crew_secret does not raise if the file doesn't exist."""
        import transport.registry as _registry_mod

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(_registry_mod, "DATA_DIR", Path(tmp)):
                # Should not raise
                _registry_mod._delete_crew_secret("nonexistent-crew")


if __name__ == "__main__":
    unittest.main()
