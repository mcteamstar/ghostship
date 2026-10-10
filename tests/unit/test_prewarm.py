"""Unit tests for the ACP prewarm operation.

Covers ``lifecycle._prewarm_crew`` (the transport-side warm-up mechanism) and
the implicit background triggers added to ``supply`` and ``schedule`` in
``server.py``.

Patch-target rule (test_lifecycle §2, the call-site principle):

* ``_prewarm_crew`` is defined in ``lifecycle.py`` and resolves
  ``_ensure_crew_running`` / ``_crew_api_with_recovery`` / ``_require_crew`` /
  ``_get_podman`` and the ``GA_PREWARM_*`` constants from lifecycle's globals,
  so those are patched ``lifecycle.X``.
* ``_bg_prewarm`` / ``_prewarm_crew`` called from ``supply``/``schedule`` are
  resolved from server's namespace, so those are patched ``server.X``.
"""

from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import MagicMock, call, patch

from tests.unit.helpers import lifecycle, server


class _RecordingPodman:
    """Podman stub recording start/stop and a scripted running state."""

    def __init__(self, running: bool = False) -> None:
        self._running = running
        self.starts: list[str] = []
        self.stops: list[str] = []

    def container_is_running(self, name: str) -> bool:
        return self._running

    def container_start(self, name: str) -> None:
        self.starts.append(name)

    def container_stop(self, name: str) -> None:
        self.stops.append(name)


class TestPrewarmCore(unittest.TestCase):
    """Core _prewarm_crew behaviour (unchanged by this change)."""

    def setUp(self) -> None:
        with lifecycle._warm_markers_lock:
            lifecycle._warm_markers.clear()

    def test_disabled_no_start_no_fork(self) -> None:
        crew = {"container": "gs-demo", "cookie": "c"}
        podman = _RecordingPodman(running=False)
        with (
            patch.object(lifecycle, "GA_PREWARM_ENABLED", False),
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(lifecycle, "_ensure_crew_running") as ensure,
            patch.object(lifecycle, "_crew_api_with_recovery") as warmup,
        ):
            result = lifecycle._prewarm_crew(crew, "demo")

        self.assertEqual(result, {"crew_id": "demo", "status": "disabled"})
        ensure.assert_not_called()
        warmup.assert_not_called()
        self.assertEqual(podman.starts, [])

    def test_stopped_crew_starts_and_warms_once(self) -> None:
        crew = {"container": "gs-demo", "cookie": "c"}
        warmed_crew = {"container": "gs-demo", "cookie": "new"}
        podman = _RecordingPodman(running=False)
        with (
            patch.object(lifecycle, "GA_PREWARM_ENABLED", True),
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(lifecycle, "_ensure_crew_running", return_value=warmed_crew) as ensure,
            patch.object(lifecycle, "_crew_api_with_recovery", return_value={}) as warmup,
        ):
            result = lifecycle._prewarm_crew(crew, "demo")

        self.assertEqual(result, {"crew_id": "demo", "status": "warmed"})
        ensure.assert_called_once_with(crew, "demo")
        self.assertEqual(warmup.call_count, 1)
        with lifecycle._warm_markers_lock:
            self.assertIn("demo", lifecycle._warm_markers)

    def test_already_warm_no_restart_no_second_warmup(self) -> None:
        crew = {"container": "gs-demo", "cookie": "c"}
        podman = _RecordingPodman(running=True)
        with lifecycle._warm_markers_lock:
            lifecycle._warm_markers["demo"] = time.monotonic()
        with (
            patch.object(lifecycle, "GA_PREWARM_ENABLED", True),
            patch.object(lifecycle, "GA_PREWARM_TTL_SECS", 300),
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(lifecycle, "_ensure_crew_running") as ensure,
            patch.object(lifecycle, "_crew_api_with_recovery") as warmup,
        ):
            result = lifecycle._prewarm_crew(crew, "demo")

        self.assertEqual(result, {"crew_id": "demo", "status": "already_warm"})
        ensure.assert_not_called()
        warmup.assert_not_called()

    def test_warmup_uses_readiness_surface_not_spawn(self) -> None:
        crew = {"container": "gs-demo", "cookie": "c"}
        podman = _RecordingPodman(running=False)
        seen: list[tuple] = []

        def record_warmup(c, cid, method, path, **kw):
            seen.append((method, path, kw))
            return {}

        with (
            patch.object(lifecycle, "GA_PREWARM_ENABLED", True),
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(lifecycle, "_ensure_crew_running", return_value=crew),
            patch.object(lifecycle, "_crew_api_with_recovery", side_effect=record_warmup),
        ):
            result = lifecycle._prewarm_crew(crew, "demo")

        self.assertEqual(result["status"], "warmed")
        self.assertEqual(len(seen), 1)
        method, path, kw = seen[0]
        self.assertEqual(method, "GET")
        self.assertNotIn("/api/spawn", path)
        self.assertNotIn("json", kw)
        self.assertEqual(lifecycle._PREWARM_WARMUP_PATH, path)

    def test_memory_gate_blocks(self) -> None:
        crew = {"container": "gs-demo", "cookie": "c"}
        podman = _RecordingPodman(running=False)
        with (
            patch.object(lifecycle, "GA_PREWARM_ENABLED", True),
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(
                lifecycle, "_ensure_crew_running",
                side_effect=RuntimeError("Insufficient available memory to start crew demo: 1.0GB free"),
            ),
            patch.object(lifecycle, "_crew_api_with_recovery") as warmup,
        ):
            result = lifecycle._prewarm_crew(crew, "demo")
        self.assertFalse(warmup.called)
        self.assertEqual(result, {"crew_id": "demo", "status": "blocked:insufficient-memory"})

    def test_active_crew_gate_blocks(self) -> None:
        crew = {"container": "gs-demo", "cookie": "c"}
        podman = _RecordingPodman(running=False)
        with (
            patch.object(lifecycle, "GA_PREWARM_ENABLED", True),
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(
                lifecycle, "_ensure_crew_running",
                side_effect=RuntimeError("Active crew limit (3) reached — wait for a running crew to idle out"),
            ),
            patch.object(lifecycle, "_crew_api_with_recovery") as warmup,
        ):
            result = lifecycle._prewarm_crew(crew, "demo")
        self.assertFalse(warmup.called)
        self.assertEqual(result, {"crew_id": "demo", "status": "blocked:active-crew-limit"})

    def test_warmup_failure_returns_error_status(self) -> None:
        with lifecycle._warm_markers_lock:
            lifecycle._warm_markers.clear()
        crew = {"container": "gs-demo", "cookie": "c"}
        podman = _RecordingPodman(running=False)
        with (
            patch.object(lifecycle, "GA_PREWARM_ENABLED", True),
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(lifecycle, "_ensure_crew_running", return_value=crew),
            patch.object(
                lifecycle, "_crew_api_with_recovery",
                side_effect=RuntimeError("gateway unresponsive"),
            ),
        ):
            result = lifecycle._prewarm_crew(crew, "demo")

        self.assertEqual(result["status"], "error:gateway unresponsive")
        with lifecycle._warm_markers_lock:
            self.assertNotIn("demo", lifecycle._warm_markers)

    def test_disabled_is_the_module_default(self) -> None:
        """GA_PREWARM_ENABLED is False when the module is loaded without the env var."""
        # The module-level constant is False by default (the demote invariant).
        self.assertIs(lifecycle.GA_PREWARM_ENABLED, False)

    def test_generic_runtime_error_returns_start_failed(self) -> None:
        """A RuntimeError whose message matches neither memory nor active-crew → blocked:start-failed."""
        with lifecycle._warm_markers_lock:
            lifecycle._warm_markers.clear()
        crew = {"container": "gs-demo", "cookie": "c"}
        podman = _RecordingPodman(running=False)
        with (
            patch.object(lifecycle, "GA_PREWARM_ENABLED", True),
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(
                lifecycle, "_ensure_crew_running",
                side_effect=RuntimeError("container image not found"),
            ),
            patch.object(lifecycle, "_crew_api_with_recovery"),
        ):
            result = lifecycle._prewarm_crew(crew, "demo")
        self.assertEqual(result, {"crew_id": "demo", "status": "blocked:start-failed"})

    def test_ttl_zero_disables_idempotency_check(self) -> None:
        """With GA_PREWARM_TTL_SECS=0 a fresh warm marker does not produce already_warm."""
        with lifecycle._warm_markers_lock:
            lifecycle._warm_markers.clear()
            lifecycle._warm_markers["demo"] = time.monotonic()  # fresh marker
        crew = {"container": "gs-demo", "cookie": "c"}
        podman = _RecordingPodman(running=True)
        with (
            patch.object(lifecycle, "GA_PREWARM_ENABLED", True),
            patch.object(lifecycle, "GA_PREWARM_TTL_SECS", 0),
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(lifecycle, "_ensure_crew_running", return_value=crew),
            patch.object(lifecycle, "_crew_api_with_recovery", return_value={}) as warmup,
        ):
            result = lifecycle._prewarm_crew(crew, "demo")
        self.assertNotEqual(result.get("status"), "already_warm")
        warmup.assert_called_once()


class TestPrewarmTTL(unittest.TestCase):
    """TTL cap tests (unchanged by this change)."""

    def test_ttl_capped_at_session_timeout(self) -> None:
        with (
            patch.object(lifecycle, "GA_PREWARM_TTL_SECS", 100000),
            patch.object(lifecycle, "GA_SESSION_TIMEOUT_SECS", 300),
        ):
            self.assertEqual(lifecycle._effective_prewarm_ttl(), 300)

    def test_ttl_below_cap_is_unchanged(self) -> None:
        with (
            patch.object(lifecycle, "GA_PREWARM_TTL_SECS", 120),
            patch.object(lifecycle, "GA_SESSION_TIMEOUT_SECS", 300),
        ):
            self.assertEqual(lifecycle._effective_prewarm_ttl(), 120)

    def test_stale_marker_beyond_capped_ttl_rewarms(self) -> None:
        with lifecycle._warm_markers_lock:
            lifecycle._warm_markers.clear()
        crew = {"container": "gs-demo", "cookie": "c"}
        podman = _RecordingPodman(running=True)
        with lifecycle._warm_markers_lock:
            lifecycle._warm_markers["demo"] = time.monotonic() - 400
        with (
            patch.object(lifecycle, "GA_PREWARM_ENABLED", True),
            patch.object(lifecycle, "GA_PREWARM_TTL_SECS", 100000),
            patch.object(lifecycle, "GA_SESSION_TIMEOUT_SECS", 300),
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(lifecycle, "_ensure_crew_running", return_value=crew),
            patch.object(lifecycle, "_crew_api_with_recovery", return_value={}) as warmup,
        ):
            result = lifecycle._prewarm_crew(crew, "demo")
        self.assertEqual(result["status"], "warmed")
        self.assertEqual(warmup.call_count, 1)


class TestPrewarmImplicitTriggers(unittest.TestCase):
    """Implicit background prewarm is fired by supply and schedule."""

    # ── supply ────────────────────────────────────────────────────────────────

    def test_supply_fires_background_prewarm(self) -> None:
        """supply() calls _bg_prewarm after issuing a presigned URL."""
        done = threading.Event()
        prewarm_calls: list[tuple] = []

        def fake_bg_prewarm(crew, crew_id):
            prewarm_calls.append((crew, crew_id))
            done.set()

        crew = {"container": "gs-demo", "cookie": "c"}
        with (
            patch.object(server, "_require_crew", return_value=crew),
            patch.object(server, "_ensure_crew_running", return_value=crew),
            patch.object(server, "_sign_upload_url", return_value="https://host/upload?x=1"),
            patch.object(server, "_security") as mock_sec,
            patch.object(server, "_bg_prewarm", side_effect=fake_bg_prewarm),
        ):
            mock_sec.audit_auth_event = MagicMock()
            result = server.supply("repo/file.txt", crew_id="demo")

        self.assertNotIn("error", result)
        self.assertEqual(len(prewarm_calls), 1)
        _, crew_id = prewarm_calls[0]
        self.assertEqual(crew_id, "demo")

    def test_supply_prewarm_exception_is_nonfatal(self) -> None:
        """An exception raised inside the _bg_prewarm thread must not fail supply.

        We test this by letting the REAL _bg_prewarm run while patching
        _prewarm_crew (which it calls) to raise; supply must still return success.
        """
        done = threading.Event()

        def raising_prewarm(crew, crew_id):
            done.set()
            raise RuntimeError("prewarm boom")

        crew = {"container": "gs-demo", "cookie": "c"}
        with (
            patch.object(server, "_require_crew", return_value=crew),
            patch.object(server, "_ensure_crew_running", return_value=crew),
            patch.object(server, "_sign_upload_url", return_value="https://host/upload?x=1"),
            patch.object(server, "_security") as mock_sec,
            patch.object(server, "_prewarm_crew", side_effect=raising_prewarm),
        ):
            mock_sec.audit_auth_event = MagicMock()
            result = server.supply("repo/file.txt", crew_id="demo")

        # supply must succeed regardless of prewarm outcome
        self.assertNotIn("error", result)
        # wait briefly for the background thread to confirm it was called
        done.wait(timeout=2.0)

    # ── schedule ──────────────────────────────────────────────────────────────

    def _minimal_schedule_patches(self, crew):
        """Return the common patches for schedule create calls."""
        return [
            patch.object(server, "_require_crew", return_value=crew),
            patch.object(server, "_ensure_crew_running", return_value=crew),
            patch.object(server, "_validate_model", return_value=None),
            patch.object(server, "_validate_agent"),
            patch.object(
                server, "_crew_api_with_recovery",
                return_value={"id": "job-1"},
            ),
            patch.object(server, "_registry_lock", threading.Lock()),
            patch.object(server, "_load_registry", return_value={"crews": {}}),
            patch.object(server, "_save_registry"),
            patch.object(server, "_upsert_crew_schedule"),
            patch.object(server, "time") if hasattr(server, "time") else
                patch("time.time", return_value=1000.0),
        ]

    def test_schedule_fires_background_prewarm(self) -> None:
        """schedule(action='create') calls _bg_prewarm after the registry write."""
        prewarm_calls: list[tuple] = []

        def fake_bg_prewarm(crew, crew_id):
            prewarm_calls.append((crew, crew_id))

        crew = {"container": "gs-demo", "cookie": "c"}
        with (
            patch.object(server, "_require_crew", return_value=crew),
            patch.object(server, "_ensure_crew_running", return_value=crew),
            patch.object(server, "_validate_model", return_value=None),
            patch.object(server, "_validate_agent"),
            patch.object(
                server, "_crew_api_with_recovery",
                return_value={"id": "job-1"},
            ),
            patch.object(server, "_registry_lock", threading.Lock()),
            patch.object(server, "_load_registry", return_value={"crews": {}}),
            patch.object(server, "_save_registry"),
            patch.object(server, "_upsert_crew_schedule"),
            patch.object(server, "_bg_prewarm", side_effect=fake_bg_prewarm),
        ):
            result = server.schedule(
                name="nightly", message="run report",
                crew_id="demo", interval=3600,
            )

        self.assertNotIn("error", result)
        self.assertEqual(len(prewarm_calls), 1)
        _, crew_id = prewarm_calls[0]
        self.assertEqual(crew_id, "demo")

    def test_schedule_prewarm_exception_is_nonfatal(self) -> None:
        """An exception raised inside the _bg_prewarm thread must not fail schedule."""
        done = threading.Event()

        def raising_prewarm(crew, crew_id):
            done.set()
            raise RuntimeError("prewarm boom")

        crew = {"container": "gs-demo", "cookie": "c"}
        with (
            patch.object(server, "_require_crew", return_value=crew),
            patch.object(server, "_ensure_crew_running", return_value=crew),
            patch.object(server, "_validate_model", return_value=None),
            patch.object(server, "_validate_agent"),
            patch.object(
                server, "_crew_api_with_recovery",
                return_value={"id": "job-1"},
            ),
            patch.object(server, "_registry_lock", threading.Lock()),
            patch.object(server, "_load_registry", return_value={"crews": {}}),
            patch.object(server, "_save_registry"),
            patch.object(server, "_upsert_crew_schedule"),
            patch.object(server, "_prewarm_crew", side_effect=raising_prewarm),
        ):
            result = server.schedule(
                name="nightly", message="run report",
                crew_id="demo", interval=3600,
            )

        self.assertNotIn("error", result)
        done.wait(timeout=2.0)


if __name__ == "__main__":
    unittest.main()
