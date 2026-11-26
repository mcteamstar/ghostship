"""Unit tests for transport/auth_refresh.py — the shared per-crew refresh operation (TRN-367).

Covers every outcome of ``refresh_crew_auth`` against a real ``CredentialStore``
and ``FakePodmanClient``:

- ``refreshed``           running crew, stored login-flow credential injected
- ``pending_on_wake``     stopped crew, stored login-flow credential
- ``current`` / ``recreate_required``  static credential matches / differs
- ``credential_missing``  nothing stored for the crew's backend and profile
- ``refresh_failed``      injection failure and comparison errors

and the properties every outcome shares: no crew is started, stopped or
recreated, only the selected crew is touched, the stored profile is read under
the credential transaction lock, and no credential value reaches the result or
a log record (including a traceback).
"""

from __future__ import annotations

import io
import json
import logging
import tarfile
import tempfile
import threading
import unittest
from unittest.mock import patch

from tests.fakes import FakePodmanClient
from transport.credentials import CredentialStore

CREW = "alpha"
CONTAINER = "gs-alpha"

# Values that must never appear in a result or a log record. None of them is
# registered with the log redaction filter, so a leak cannot be masked by it.
STORED_SECRET = "stored-static-secret-7f3a91"
OLD_CONTAINER_SECRET = "old-container-secret-5b2d40"
ALL_SECRETS = (STORED_SECRET, OLD_CONTAINER_SECRET)

# (backend, method, container environment variable) for every static method.
STATIC_METHODS = (
    ("kiro", "api-key", "KIRO_API_KEY"),
    ("codex", "api-key", "OPENAI_API_KEY"),
    ("claude", "api-key", "ANTHROPIC_API_KEY"),
    ("claude", "setup-token", "CLAUDE_CODE_OAUTH_TOKEN"),
)

RESULT_KEYS = {"status", "crew_id", "backend", "profile", "message"}


def _tar(data: bytes = b"synthetic-archive-member") -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as archive:
        info = tarfile.TarInfo("auth.json")
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class _Records(logging.Handler):
    """Collects raw log records from every logger, with no redaction applied."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def rendered(self) -> list[str]:
        """Each record as a handler would write it, traceback included."""
        formatter = logging.Formatter()
        return [formatter.format(record) for record in self.records]


class _RefreshHarness(unittest.TestCase):
    """Setup-only base: a temp credential store, a fake Podman and a fake registry."""

    def setUp(self) -> None:
        import transport.auth_refresh as refresh
        import transport.launcher as launcher
        import transport.lifecycle as lifecycle
        import transport.login as login

        self.refresh, self.launcher, self.lifecycle, self.login = refresh, launcher, lifecycle, login
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = CredentialStore(tmp.name)
        self.podman = FakePodmanClient()
        self.crews: dict[str, dict] = {}
        self.injected: list[tuple[str, str, object]] = []

        def record(kind):
            def _inject(podman, container, data):
                self.injected.append((kind, container, data))
            return _inject

        for target, name, value in (
            (login, "_cred_store", self.store),
            (refresh, "_get_podman", lambda: self.podman),
            (refresh, "_get_crew", self._get_crew),
            (lifecycle, "_inject_auth", record("kiro")),
            (lifecycle, "_inject_claude_auth", record("claude")),
            (lifecycle, "_inject_codex_auth", record("codex")),
        ):
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        self.records = _Records()
        root = logging.getLogger()
        root.addHandler(self.records)
        self.addCleanup(root.removeHandler, self.records)
        self._root_level = root.level
        root.setLevel(logging.DEBUG)
        self.addCleanup(root.setLevel, self._root_level)

    # ── fixtures ──────────────────────────────────────────────────────────────

    def _get_crew(self, crew_id: str) -> dict:
        if crew_id not in self.crews:
            raise KeyError(crew_id)
        return self.crews[crew_id]

    def add_crew(
        self,
        crew_id: str = CREW,
        *,
        backend: str = "kiro",
        profile: str | None = None,
        running: bool = True,
        env: list[str] | None = None,
    ) -> str:
        """Register a crew and its container; *env* is the container's environment."""
        container = f"gs-{crew_id}"
        entry = {
            "container": container,
            "status": "running" if running else "stopped",
            "acp_backend": backend,
        }
        if profile is not None:
            entry["acp_profile"] = profile
        self.crews[crew_id] = entry
        self.podman.add_container(
            container,
            running=running,
            inspect={"Name": container, "Config": {"Env": list(env or [])}},
        )
        return container

    def refresh_crew(self, crew_id: str = CREW) -> dict:
        return self.refresh.refresh_crew_auth(crew_id)

    # ── shared assertions ─────────────────────────────────────────────────────

    def assert_crew_untouched(self) -> None:
        """No refresh outcome may start, stop, remove or recreate a container."""
        for method in ("container_start", "container_stop", "container_remove", "container_create"):
            self.assertEqual(self.podman.calls_for(method), [], method)

    def assert_no_secret(self, result: dict | None = None) -> None:
        """No credential value in the result, any log record or any traceback."""
        texts = list(self.records.rendered())
        for record in self.records.records:
            texts.append(record.getMessage())
            texts.append(str(record.msg))
            texts.append(str(record.args))
            texts.append(str(record.exc_text))
        if result is not None:
            texts.append(json.dumps(result))
        for text in texts:
            for secret in ALL_SECRETS:
                self.assertNotIn(secret, text)

    def assert_result_shape(self, result: dict, status: str) -> None:
        self.assertEqual(result["status"], status)
        self.assertEqual(set(result), RESULT_KEYS)
        self.assertEqual(result["crew_id"], CREW)
        self.assertIsInstance(result["message"], str)
        self.assertTrue(result["message"])


class TestRunningFlowCrewIsRefreshed(_RefreshHarness):
    """A running crew with a stored login-flow credential gets it injected."""

    CASES = (
        ("kiro", "builder-id", "kiro"),
        ("kiro", "identity-center", "kiro"),
        ("claude", "oauth", "claude"),
        ("codex", "chatgpt", "codex"),
    )

    def _store(self, backend: str, method: str, profile: str = "default"):
        if backend == "kiro":
            payload = "synthetic-kiro-auth-rows"
            self.store.put(backend, method, payload, profile=profile)
            return payload
        payload = _tar()
        self.store.put(backend, method, payload, profile=profile)
        return payload

    def test_refreshed_for_each_flow_method(self):
        for backend, method, kind in self.CASES:
            with self.subTest(backend=backend, method=method):
                self.injected.clear()
                container = self.add_crew(backend=backend)
                payload = self._store(backend, method)
                result = self.refresh_crew()
                self.assert_result_shape(result, "refreshed")
                self.assertEqual((result["backend"], result["profile"]), (backend, "default"))
                self.assertEqual(self.injected, [(kind, container, payload)])
                self.assert_crew_untouched()
                self.assert_no_secret(result)

    def test_recorded_profile_selects_the_credential(self):
        container = self.add_crew(backend="codex", profile="work")
        self.store.put("codex", "chatgpt", _tar(b"default-archive"))
        work = _tar(b"work-archive")
        self.store.put("codex", "chatgpt", work, profile="work")
        result = self.refresh_crew()
        self.assertEqual(result["status"], "refreshed")
        self.assertEqual(result["profile"], "work")
        self.assertEqual(self.injected, [("codex", container, work)])

    def test_only_the_selected_crew_is_modified(self):
        selected = self.add_crew(CREW, backend="claude", profile="work")
        self.add_crew("bravo", backend="claude", profile="work")
        self.add_crew("charlie", backend="claude", profile="personal")
        self.add_crew("delta", backend="codex", profile="work")
        self.store.put("claude", "oauth", _tar(), profile="work")
        self.refresh_crew()
        self.assertEqual([entry[1] for entry in self.injected], [selected])

    def test_missing_backend_and_profile_default_to_kiro_default(self):
        container = self.add_crew(backend="kiro")
        del self.crews[CREW]["acp_backend"]
        self.store.put("kiro", "builder-id", "synthetic-rows")
        result = self.refresh_crew()
        self.assertEqual((result["status"], result["backend"], result["profile"]), ("refreshed", "kiro", "default"))
        self.assertEqual(self.injected, [("kiro", container, "synthetic-rows")])

    def test_kiro_sign_in_state_is_cleared_only_after_a_kiro_injection(self):
        with patch("transport.kiro_signin.clear") as clear:
            self.add_crew(backend="kiro")
            self.store.put("kiro", "builder-id", "synthetic-rows")
            self.refresh_crew()
            clear.assert_called_once_with(CREW)

        with patch("transport.kiro_signin.clear") as clear:
            self.add_crew(backend="codex")
            self.store.put("codex", "chatgpt", _tar())
            self.refresh_crew()
            clear.assert_not_called()

        with patch("transport.kiro_signin.clear") as clear:
            self.add_crew(backend="kiro")
            self.store.put("kiro", "builder-id", "synthetic-rows")
            with patch.object(self.lifecycle, "_inject_auth", side_effect=OSError("exec failed")):
                self.refresh_crew()
            clear.assert_not_called()

    def test_kiro_sign_in_clear_failure_does_not_fail_the_refresh(self):
        self.add_crew(backend="kiro")
        self.store.put("kiro", "builder-id", "synthetic-rows")
        with patch("transport.kiro_signin.clear", side_effect=RuntimeError("registry busy")):
            result = self.refresh_crew()
        self.assertEqual(result["status"], "refreshed")


class TestStoppedFlowCrew(_RefreshHarness):
    """A stopped crew is left stopped; it receives the credential when it wakes."""

    def test_stopped_flow_crew_is_pending_on_wake(self):
        for backend, method in (
            ("kiro", "builder-id"), ("kiro", "identity-center"), ("claude", "oauth"), ("codex", "chatgpt"),
        ):
            with self.subTest(backend=backend, method=method):
                self.add_crew(backend=backend, running=False)
                self.store.put(backend, method, "synthetic-rows" if backend == "kiro" else _tar())
                result = self.refresh_crew()
                self.assert_result_shape(result, "pending_on_wake")
                self.assertEqual(self.injected, [])
                self.assertFalse(self.podman.container_is_running(f"gs-{CREW}"))
                self.assert_crew_untouched()
                self.assert_no_secret(result)

    def test_stopped_crew_with_leftover_static_value_cannot_wake_so_recreate_is_required(self):
        # The wake path refuses this crew, so promising an injection on wake would mislead.
        self.add_crew(backend="codex", running=False, env=[f"OPENAI_API_KEY={OLD_CONTAINER_SECRET}"])
        self.store.put("codex", "chatgpt", _tar())
        result = self.refresh_crew()
        self.assert_result_shape(result, "recreate_required")
        self.assertIn("cannot wake", result["message"])
        self.assertEqual(self.injected, [])
        self.assert_no_secret(result)


class TestStaticCredential(_RefreshHarness):
    """Static values are fixed in the container: compare, never change."""

    def test_matching_static_credential_is_current(self):
        for backend, method, variable in STATIC_METHODS:
            for running in (True, False):
                with self.subTest(backend=backend, method=method, running=running):
                    self.podman.calls.clear()
                    self.add_crew(backend=backend, running=running, env=["PATH=/usr/bin", f"{variable}={STORED_SECRET}"])
                    self.store.put(backend, method, STORED_SECRET)
                    result = self.refresh_crew()
                    self.assert_result_shape(result, "current")
                    self.assertEqual(self.injected, [])
                    self.assert_crew_untouched()
                    self.assert_no_secret(result)

    def test_changed_static_value_requires_recreation(self):
        for backend, method, variable in STATIC_METHODS:
            for running in (True, False):
                with self.subTest(backend=backend, method=method, running=running):
                    self.podman.calls.clear()
                    self.add_crew(backend=backend, running=running, env=[f"{variable}={OLD_CONTAINER_SECRET}"])
                    self.store.put(backend, method, STORED_SECRET)
                    result = self.refresh_crew()
                    self.assert_result_shape(result, "recreate_required")
                    self.assertEqual(self.injected, [])
                    self.assert_crew_untouched()
                    self.assertEqual(self.podman.container_is_running(f"gs-{CREW}"), running)
                    self.assert_no_secret(result)

    def test_static_value_absent_from_container_requires_recreation(self):
        # The crew was launched with a login flow; a static credential cannot be added in place.
        self.add_crew(backend="claude", env=["PATH=/usr/bin"])
        self.store.put("claude", "setup-token", STORED_SECRET)
        result = self.refresh_crew()
        self.assert_result_shape(result, "recreate_required")
        self.assert_crew_untouched()

    def test_changed_static_method_requires_recreation(self):
        # api-key -> setup-token: the container still carries the other variable.
        self.add_crew(backend="claude", env=[f"ANTHROPIC_API_KEY={OLD_CONTAINER_SECRET}"])
        self.store.put("claude", "setup-token", STORED_SECRET)
        result = self.refresh_crew()
        self.assert_result_shape(result, "recreate_required")
        self.assert_no_secret(result)

    def test_flow_credential_with_leftover_static_value_requires_recreation(self):
        # Switching a profile from static to a login flow leaves the old value in the container.
        for backend, method, variable in (
            ("kiro", "builder-id", "KIRO_API_KEY"),
            ("claude", "oauth", "CLAUDE_CODE_OAUTH_TOKEN"),
            ("codex", "chatgpt", "OPENAI_API_KEY"),
        ):
            with self.subTest(backend=backend, method=method):
                self.add_crew(backend=backend, env=[f"{variable}={OLD_CONTAINER_SECRET}"])
                self.store.put(backend, method, "synthetic-rows" if backend == "kiro" else _tar())
                result = self.refresh_crew()
                self.assert_result_shape(result, "recreate_required")
                self.assertEqual(self.injected, [])
                self.assert_crew_untouched()
                self.assert_no_secret(result)

    def test_empty_leftover_static_variable_does_not_force_recreation(self):
        self.add_crew(backend="codex", env=["OPENAI_API_KEY="])
        self.store.put("codex", "chatgpt", _tar())
        self.assertEqual(self.refresh_crew()["status"], "refreshed")

    def test_recreation_guidance_names_the_workspace_preserving_workflow(self):
        self.add_crew(backend="codex", running=True, env=[f"OPENAI_API_KEY={OLD_CONTAINER_SECRET}"])
        self.store.put("codex", "api-key", STORED_SECRET)
        running = self.refresh_crew()["message"]
        for word in ("evac", "nuke", "launch", "supply", "docs/auth.md"):
            self.assertIn(word, running)

        self.add_crew(backend="codex", running=False, env=[f"OPENAI_API_KEY={OLD_CONTAINER_SECRET}"])
        stopped = self.refresh_crew()["message"]
        for word in ("evac", "nuke", "launch", "supply", "docs/auth.md", "Restore", "wake"):
            self.assertIn(word, stopped)
        self.assertNotEqual(running, stopped)

    def test_comparison_is_constant_time_and_never_ordinary_equality(self):
        self.add_crew(backend="codex", env=[f"OPENAI_API_KEY={STORED_SECRET}"])
        self.store.put("codex", "api-key", STORED_SECRET)
        with patch.object(self.launcher.hmac, "compare_digest", wraps=self.launcher.hmac.compare_digest) as compare:
            self.assertEqual(self.refresh_crew()["status"], "current")
        compare.assert_called_once()
        for argument in compare.call_args.args:
            self.assertIsInstance(argument, bytes)


class TestCredentialMissing(_RefreshHarness):

    def test_missing_credential_is_reported_without_touching_the_crew(self):
        self.add_crew(backend="claude", profile="work")
        result = self.refresh_crew()
        self.assert_result_shape(result, "credential_missing")
        self.assertIn("claude profile 'work'", result["message"])
        self.assertIn("ghostship auth login claude --profile work", result["message"])
        self.assertEqual(self.injected, [])
        self.assertEqual(self.podman.calls_for("container_inspect"), [])
        self.assert_crew_untouched()

    def test_default_profile_guidance_omits_the_profile_flag(self):
        self.add_crew(backend="kiro")
        message = self.refresh_crew()["message"]
        self.assertIn("ghostship auth login kiro`", message)
        self.assertNotIn("--profile", message)

    def test_named_profile_never_falls_back_to_the_default_credential(self):
        self.add_crew(backend="codex", profile="work")
        self.store.put("codex", "chatgpt", _tar())
        result = self.refresh_crew()
        self.assertEqual(result["status"], "credential_missing")
        self.assertEqual(self.injected, [])

    def test_stopped_crew_with_missing_credential_is_reported_missing(self):
        self.add_crew(backend="kiro", running=False)
        self.assertEqual(self.refresh_crew()["status"], "credential_missing")


class TestInjectionFailure(_RefreshHarness):

    def test_injection_failure_is_reported_and_leaves_the_crew_running(self):
        for backend, method, injector in (
            ("kiro", "builder-id", "_inject_auth"),
            ("claude", "oauth", "_inject_claude_auth"),
            ("codex", "chatgpt", "_inject_codex_auth"),
        ):
            with self.subTest(backend=backend):
                self.podman.calls.clear()
                self.add_crew(backend=backend)
                self.store.put(backend, method, "synthetic-rows" if backend == "kiro" else _tar())
                leaked = f"exec failed: stderr echoed {STORED_SECRET} and {OLD_CONTAINER_SECRET}"
                with patch.object(self.lifecycle, injector, side_effect=RuntimeError(leaked)):
                    result = self.refresh_crew()
                self.assert_result_shape(result, "refresh_failed")
                self.assertIn("left running", result["message"])
                self.assertTrue(self.podman.container_is_running(f"gs-{CREW}"))
                self.assertEqual(self.crews[CREW]["status"], "running")
                self.assert_crew_untouched()
                self.assert_no_secret(result)

    def test_invalid_stored_archive_is_a_failed_refresh_not_an_error(self):
        self.add_crew(backend="codex")
        self.store.put("codex", "chatgpt", b"not a tar archive and not base64 either!")
        result = self.refresh_crew()
        self.assert_result_shape(result, "refresh_failed")
        self.assertEqual(self.injected, [])

    def test_failure_is_logged_by_exception_class_only(self):
        self.add_crew(backend="kiro")
        self.store.put("kiro", "builder-id", "synthetic-rows")
        with patch.object(self.lifecycle, "_inject_auth", side_effect=OSError("secret detail")):
            self.refresh_crew()
        warnings = [r for r in self.records.records if r.levelno == logging.WARNING]
        self.assertEqual(len(warnings), 1)
        self.assertIsNone(warnings[0].exc_info)
        self.assertIn("OSError", warnings[0].getMessage())
        self.assertNotIn("secret detail", "\n".join(self.records.rendered()))


class TestComparisonError(_RefreshHarness):
    """An error while comparing a static credential reports refresh_failed and leaks nothing."""

    def _assert_failed_without_leak(self, result: dict) -> None:
        self.assert_result_shape(result, "refresh_failed")
        self.assertIn("not changed", result["message"])
        self.assertEqual(self.injected, [])
        self.assert_crew_untouched()
        self.assert_no_secret(result)
        failures = [r for r in self.records.records if r.levelno >= logging.WARNING]
        self.assertTrue(failures)
        for record in failures:
            self.assertIsNone(record.exc_info)  # no traceback to carry the value
            self.assertIsNone(record.exc_text)

    def test_inspect_error_that_echoes_the_environment(self):
        self.add_crew(backend="codex", env=[f"OPENAI_API_KEY={OLD_CONTAINER_SECRET}"])
        self.store.put("codex", "api-key", STORED_SECRET)
        echoed = RuntimeError(f"inspect failed: Env=['OPENAI_API_KEY={OLD_CONTAINER_SECRET}'] {STORED_SECRET}")
        with patch.object(self.podman, "container_inspect", side_effect=echoed):
            result = self.refresh_crew()
        self._assert_failed_without_leak(result)

    def test_constant_time_comparison_error_that_echoes_the_values(self):
        self.add_crew(backend="codex", env=[f"OPENAI_API_KEY={OLD_CONTAINER_SECRET}"])
        self.store.put("codex", "api-key", STORED_SECRET)
        echoed = TypeError(f"cannot compare {OLD_CONTAINER_SECRET!r} with {STORED_SECRET!r}")
        with patch.object(self.launcher.hmac, "compare_digest", side_effect=echoed):
            result = self.refresh_crew()
        self._assert_failed_without_leak(result)

    def test_malformed_inspect_output(self):
        self.add_crew(backend="codex")
        self.store.put("codex", "api-key", STORED_SECRET)
        with patch.object(self.podman, "container_inspect", return_value={"Config": None}):
            result = self.refresh_crew()
        self.assert_result_shape(result, "refresh_failed")
        self.assert_no_secret(result)

    def test_missing_container_is_a_failed_refresh(self):
        self.add_crew(backend="codex")
        self.store.put("codex", "api-key", STORED_SECRET)
        self.podman.container_remove(f"gs-{CREW}")
        self.podman.calls.clear()
        result = self.refresh_crew()
        self.assert_result_shape(result, "refresh_failed")
        self.assert_crew_untouched()

    def test_podman_unavailable_is_a_failed_refresh(self):
        self.add_crew(backend="codex", env=[f"OPENAI_API_KEY={STORED_SECRET}"])
        self.store.put("codex", "api-key", STORED_SECRET)
        with patch.object(self.refresh, "_get_podman", side_effect=RuntimeError("socket gone")):
            result = self.refresh_crew()
        self.assert_result_shape(result, "refresh_failed")

    def test_credential_store_error_is_a_failed_refresh(self):
        self.add_crew(backend="kiro")
        with patch.object(self.store, "get", side_effect=OSError(f"unreadable {STORED_SECRET}")):
            result = self.refresh_crew()
        self.assert_result_shape(result, "refresh_failed")
        self.assert_no_secret(result)
        self.assertEqual(self.podman.calls_for("container_inspect"), [])

    def test_unsupported_stored_method_is_a_failed_refresh(self):
        self.add_crew(backend="codex")
        with patch.object(self.store, "get", return_value={"method": "future-method", "payload": b"x"}):
            result = self.refresh_crew()
        self.assert_result_shape(result, "refresh_failed")
        self.assertIn("ghostship auth login codex", result["message"])
        self.assertEqual(self.injected, [])


class TestUnknownCrew(_RefreshHarness):

    def test_unknown_crew_raises_and_changes_nothing(self):
        self.add_crew("bravo", backend="kiro")
        self.store.put("kiro", "builder-id", "synthetic-rows")
        with self.assertRaises(self.refresh.CrewNotFound):
            self.refresh_crew("missing")
        self.assertEqual(self.injected, [])
        self.assertEqual(self.podman.calls, [])
        self.assertEqual(self.store.get("kiro")["payload"], b"synthetic-rows")

    def test_unknown_crew_does_not_wait_for_the_credential_lock(self):
        done = threading.Event()

        def call():
            try:
                self.refresh_crew("missing")
            except self.refresh.CrewNotFound:
                pass
            done.set()

        with self.login._credential_transaction_lock:
            worker = threading.Thread(target=call, daemon=True)
            worker.start()
            self.assertTrue(done.wait(2.0))
        worker.join(2.0)

    def test_crew_removed_while_waiting_for_the_lock_is_not_found(self):
        self.add_crew(backend="kiro")
        self.store.put("kiro", "builder-id", "synthetic-rows")
        outcome: dict = {}

        def call():
            try:
                outcome["result"] = self.refresh_crew()
            except self.refresh.CrewNotFound:
                outcome["not_found"] = True

        with self.login._credential_transaction_lock:
            worker = threading.Thread(target=call, daemon=True)
            worker.start()
            worker.join(0.2)
            self.assertTrue(worker.is_alive())
            del self.crews[CREW]  # nuked while the refresh waited
        worker.join(5.0)
        self.assertEqual(outcome, {"not_found": True})
        self.assertEqual(self.injected, [])


class TestSerializationWithCredentialChanges(_RefreshHarness):
    """The refresh runs under the credential transaction lock and reads the profile inside it."""

    def _refresh_in_thread(self) -> tuple[threading.Thread, dict]:
        outcome: dict = {}

        def call():
            outcome["result"] = self.refresh_crew()

        worker = threading.Thread(target=call, daemon=True)
        worker.start()
        return worker, outcome

    def test_refresh_waits_for_an_in_flight_replacement_and_injects_the_new_credential(self):
        container = self.add_crew(backend="codex", profile="work")
        stale = _tar(b"stale-archive")
        fresh = _tar(b"fresh-archive")
        self.store.put("codex", "chatgpt", stale, profile="work")

        with self.login._credential_transaction_lock:
            worker, outcome = self._refresh_in_thread()
            worker.join(0.3)
            self.assertTrue(worker.is_alive(), "refresh must wait for the credential transaction")
            self.assertEqual(self.injected, [])
            # The replacement commits while the refresh is queued.
            self.store.put("codex", "chatgpt", fresh, profile="work")
        worker.join(5.0)

        self.assertEqual(outcome["result"]["status"], "refreshed")
        self.assertEqual(self.injected, [("codex", container, fresh)])

    def test_refresh_waits_for_an_in_flight_logout_and_injects_nothing(self):
        self.add_crew(backend="claude")
        self.store.put("claude", "oauth", _tar())

        with self.login._credential_transaction_lock:
            worker, outcome = self._refresh_in_thread()
            worker.join(0.3)
            self.assertTrue(worker.is_alive())
            self.store.delete("claude")  # the logout commits while the refresh is queued
        worker.join(5.0)

        self.assertEqual(outcome["result"]["status"], "credential_missing")
        self.assertEqual(self.injected, [])

    def test_credential_changes_wait_while_a_refresh_is_injecting(self):
        self.add_crew(backend="kiro")
        self.store.put("kiro", "builder-id", "synthetic-rows")
        entered, release = threading.Event(), threading.Event()
        replaced = threading.Event()

        def slow_inject(podman, container, data):
            entered.set()
            self.assertTrue(release.wait(5.0))
            self.injected.append(("kiro", container, data))

        def replace():
            with self.login._credential_transaction_lock:
                self.store.put("kiro", "builder-id", "newer-rows")
                replaced.set()

        with patch.object(self.lifecycle, "_inject_auth", slow_inject):
            worker, outcome = self._refresh_in_thread()
            self.assertTrue(entered.wait(5.0))
            writer = threading.Thread(target=replace, daemon=True)
            writer.start()
            self.assertFalse(replaced.wait(0.3), "replacement must wait for the injection")
            release.set()
            worker.join(5.0)
            writer.join(5.0)

        self.assertEqual(outcome["result"]["status"], "refreshed")
        self.assertEqual(self.injected[0][2], "synthetic-rows")
        self.assertTrue(replaced.is_set())
        self.assertEqual(self.store.get("kiro")["payload"], b"newer-rows")

    def test_lock_is_released_after_every_outcome(self):
        self.add_crew(backend="kiro")
        self.refresh_crew()  # credential_missing
        self.store.put("kiro", "builder-id", "synthetic-rows")
        with patch.object(self.lifecycle, "_inject_auth", side_effect=OSError("x")):
            self.refresh_crew()  # refresh_failed
        self.refresh_crew()  # refreshed
        acquired = self.login._credential_transaction_lock.acquire(timeout=1.0)
        self.assertTrue(acquired)
        self.login._credential_transaction_lock.release()


class TestEveryOutcomeIsSecretFree(_RefreshHarness):
    """One pass over all six outcomes: the result carries no credential and logs are clean."""

    def test_all_outcomes_have_the_same_safe_shape(self):
        seen = {}

        # refreshed
        self.add_crew("a", backend="codex")
        self.store.put("codex", "chatgpt", _tar(STORED_SECRET.encode()), profile="default")
        seen["refreshed"] = self.refresh.refresh_crew_auth("a")
        # pending_on_wake
        self.add_crew("b", backend="codex", running=False)
        seen["pending_on_wake"] = self.refresh.refresh_crew_auth("b")
        # current
        self.store.put("claude", "api-key", STORED_SECRET)
        self.add_crew("c", backend="claude", env=[f"ANTHROPIC_API_KEY={STORED_SECRET}"])
        seen["current"] = self.refresh.refresh_crew_auth("c")
        # recreate_required
        self.add_crew("d", backend="claude", env=[f"ANTHROPIC_API_KEY={OLD_CONTAINER_SECRET}"])
        seen["recreate_required"] = self.refresh.refresh_crew_auth("d")
        # credential_missing
        self.add_crew("e", backend="kiro")
        seen["credential_missing"] = self.refresh.refresh_crew_auth("e")
        # refresh_failed
        self.add_crew("f", backend="codex")
        with patch.object(self.lifecycle, "_inject_codex_auth", side_effect=OSError(STORED_SECRET)):
            seen["refresh_failed"] = self.refresh.refresh_crew_auth("f")

        self.assertEqual(set(seen), set(self.refresh.OUTCOMES))
        for status, result in seen.items():
            with self.subTest(status=status):
                self.assertEqual(result["status"], status)
                self.assertEqual(set(result), RESULT_KEYS)
                self.assert_no_secret(result)
        self.assert_crew_untouched()


class TestStaticCredentialMismatchHelper(unittest.TestCase):
    """transport.launcher.static_credential_mismatch backs both the wake path and refresh."""

    def setUp(self):
        import transport.launcher as launcher
        self.launcher = launcher
        self.podman = FakePodmanClient()

    def _mismatch(self, backend, method, payload, env):
        self.podman.add_container("c", inspect={"Config": {"Env": env}})
        return self.launcher.static_credential_mismatch(
            self.podman, "c", backend, {"method": method, "payload": payload},
        )

    def test_consistent_static_environment(self):
        self.assertIsNone(self._mismatch("codex", "api-key", b"v1", ["OPENAI_API_KEY=v1"]))

    def test_changed_value_and_absent_value(self):
        self.assertEqual(self._mismatch("codex", "api-key", b"v2", ["OPENAI_API_KEY=v1"]), "value")
        self.assertEqual(self._mismatch("codex", "api-key", b"v1", []), "value")

    def test_duplicate_variable_is_a_mismatch(self):
        env = ["OPENAI_API_KEY=v1", "OPENAI_API_KEY=v1"]
        self.assertEqual(self._mismatch("codex", "api-key", b"v1", env), "value")

    def test_flow_credential_with_leftover_static_variable(self):
        self.assertEqual(self._mismatch("codex", "chatgpt", b"x", ["OPENAI_API_KEY=old"]), "method")
        self.assertIsNone(self._mismatch("codex", "chatgpt", b"x", ["OPENAI_API_KEY=", "PATH=/bin"]))

    def test_str_payload_is_accepted(self):
        self.assertIsNone(self._mismatch("kiro", "api-key", "v1", ["KIRO_API_KEY=v1"]))

    def test_non_ascii_values_are_compared_without_error(self):
        self.assertIsNone(self._mismatch("kiro", "api-key", "clé-é".encode(), ["KIRO_API_KEY=clé-é"]))
        self.assertEqual(self._mismatch("kiro", "api-key", b"plain", ["KIRO_API_KEY=clé-é"]), "value")

    def test_is_static_credential(self):
        for backend, method, _variable in STATIC_METHODS:
            self.assertTrue(self.launcher.is_static_credential(backend, method))
        for backend, method in (("kiro", "builder-id"), ("kiro", "identity-center"), ("claude", "oauth"), ("codex", "chatgpt")):
            self.assertFalse(self.launcher.is_static_credential(backend, method))
        self.assertFalse(self.launcher.is_static_credential("kiro", None))

    def test_wake_path_raises_the_same_two_messages(self):
        self.podman.add_container("c", inspect={"Config": {"Env": ["OPENAI_API_KEY=old"]}})
        with self.assertRaisesRegex(RuntimeError, "static credential changed"):
            self.launcher._validate_static_credential(
                self.podman, "c", "codex", {"method": "api-key", "payload": b"new"},
            )
        with self.assertRaisesRegex(RuntimeError, "credential method changed"):
            self.launcher._validate_static_credential(
                self.podman, "c", "codex", {"method": "chatgpt", "payload": b"x"},
            )
        self.assertIsNone(self.launcher._validate_static_credential(
            self.podman, "c", "codex", {"method": "api-key", "payload": b"old"},
        ))


if __name__ == "__main__":
    unittest.main()
