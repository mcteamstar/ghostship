"""Unit tests for transport/lifecycle.py crew lifecycle management (TRN-246).

Covers the four top-level lifecycle operations and their state transitions,
using ``FakePodmanClient`` and the autouse conftest stubs (no real Podman
socket, no filesystem I/O):

- ``TestSecretIdentifier``        — ``_secret_identifier`` pure-function tests
- ``TestCleanupCrew``             — ``_cleanup_crew`` teardown + fault isolation
- ``TestEnsureRunning``           — ``CrewLauncher.ensure_running`` happy path +
                                     ``_NUKED_DURING_RESTART`` sentinel
- ``TestEnsureRunningConcurrency``— leader/waiter serialisation, generation
                                     counter, leader-exception propagation
- ``TestActiveLimit``             — ``CrewLauncher._check_active_limit`` gate
- ``TestMemoryGate``              — ``CrewLauncher._check_memory_gate`` gate
- ``TestStateTransitions``        — end-to-end state graph driven through the fake

Design (see change design.md):
- D1: test ``CrewLauncher`` directly, not through the ``lifecycle`` wrapper.
- D2: ``threading.Thread`` for concurrency tests.
- D3: patch ``lifecycle.GA_MAX_ACTIVE_CREWS`` / ``lifecycle.GA_MIN_FREE_MEM_GB``
      for the gate tests.
- D4: real ``CrewRegistry`` backed by the conftest ``_load_registry`` /
      ``_save_registry`` patches; pre-seed ``registry._reg["crews"]`` directly.
- D5: monkey-patch ``FakePodmanClient`` methods for fault-isolation tests.

``ensure_running`` resolves its collaborators lazily at call time: it uses the
module-level ``transport.lifecycle._get_podman`` and the module-level
``registry`` singleton, and imports its helper functions from
``transport.lifecycle``. Tests therefore patch those module attributes rather
than passing collaborators in.
"""

from __future__ import annotations

import threading
import unittest
from unittest.mock import patch

from tests.fakes import FakePodmanClient


# ── Shared helpers ────────────────────────────────────────────────────────────

CREW_ID = "test"
CONTAINER = "gs-test"


def _patch_registry_backing(test, reg_mod, crews):
    """Make ``with registry:`` observe and mutate a persistent ``crews`` map.

    ``CrewRegistry.__enter__`` sets ``self._reg = _load_registry()`` and
    ``__exit__`` calls ``_save_registry(self._reg)``. The autouse
    ``_block_registry_io`` fixture already stubs both, but it returns a FRESH
    ``{"crews": {}}`` each enter, so a seeded entry would be discarded and
    status writes made inside a ``with`` block would be lost on exit.

    This patches ``_load_registry`` to return ONE stable backing dict on every
    enter (so writes made against ``self._reg`` persist across blocks) and keeps
    ``_save_registry`` a no-op. The patch is registered for teardown via the
    test's ``addCleanup``. Returns the backing ``crews`` dict for assertions.
    """
    backing = {"crews": crews}
    p_load = patch.object(reg_mod, "_load_registry", return_value=backing)
    p_save = patch.object(reg_mod, "_save_registry")
    p_load.start()
    p_save.start()
    test.addCleanup(p_load.stop)
    test.addCleanup(p_save.stop)
    return backing["crews"]


# ── TestSecretIdentifier ──────────────────────────────────────────────────────

class TestSecretIdentifier(unittest.TestCase):
    """_secret_identifier: opaque, deterministic, non-reversible label."""

    def _ident(self, value: str) -> str:
        from transport.lifecycle import _secret_identifier
        return _secret_identifier(value)

    def test_returns_sha256_prefix(self):
        """Result starts with ``sha256:`` and suffix is 16 hex chars."""
        result = self._ident("some-admiral-secret")
        self.assertTrue(result.startswith("sha256:"))
        suffix = result[len("sha256:"):]
        self.assertEqual(len(suffix), 16)
        self.assertTrue(all(c in "0123456789abcdef" for c in suffix),
                        f"suffix not lowercase hex: {suffix!r}")

    def test_different_inputs_differ(self):
        self.assertNotEqual(self._ident("secret-a"), self._ident("secret-b"))

    def test_deterministic(self):
        self.assertEqual(self._ident("same-value"), self._ident("same-value"))


# ── TestCleanupCrew ───────────────────────────────────────────────────────────

class TestCleanupCrew(unittest.TestCase):
    """_cleanup_crew: best-effort teardown of all 4 resource types."""

    def setUp(self):
        from transport.lifecycle import _cleanup_crew
        self._cleanup = _cleanup_crew
        self.podman = FakePodmanClient()
        self.podman.add_container("gs-abc", running=True)
        self.podman.volume_create("gs-vol-abc")
        self.podman.volume_create("gs-home-abc")
        self.podman.secret_create("admiral-pubkey-abc", b"ssh-ed25519 AAAA...")

    def _methods_called(self):
        return [c[0] for c in self.podman.calls]

    def test_full_cleanup_removes_all_resources(self):
        self._cleanup(self.podman, "gs-abc", "gs-vol-abc", "gs-home-abc")
        called = self._methods_called()
        self.assertIn("container_stop", called)
        self.assertIn("container_remove", called)
        self.assertEqual(len(self.podman.calls_for("volume_remove")), 2)
        self.assertIn("secret_remove", called)
        # Resources gone from the fake afterwards.
        self.assertFalse(self.podman.container_exists("gs-abc"))
        self.assertNotIn("gs-vol-abc", self.podman._volumes)
        self.assertNotIn("gs-home-abc", self.podman._volumes)
        self.assertNotIn("admiral-pubkey-abc", self.podman._secrets)

    def test_container_stop_failure_does_not_abort_volume_removal(self):
        def _boom(name):
            self.podman.calls.append(("container_stop", name))
            raise RuntimeError("container already gone")
        self.podman.container_stop = _boom  # D5: monkey-patch the instance
        self._cleanup(self.podman, "gs-abc", "gs-vol-abc", "gs-home-abc")
        self.assertEqual(len(self.podman.calls_for("volume_remove")), 2)

    def test_volume_remove_failure_does_not_abort_secret_removal(self):
        def _boom(name):
            self.podman.calls.append(("volume_remove", name))
            raise RuntimeError("volume in use")
        self.podman.volume_remove = _boom
        self._cleanup(self.podman, "gs-abc", "gs-vol-abc", "gs-home-abc")
        self.assertTrue(self.podman.was_called("secret_remove"))

    def test_non_crew_container_skips_secret_removal(self):
        # Container name does not start with CREW_CONTAINER_PREFIX ("gs-").
        self._cleanup(self.podman, "other-abc", "gs-vol-abc", "gs-home-abc")
        self.assertFalse(self.podman.was_called("secret_remove"))


# ── ensure_running patch harness ──────────────────────────────────────────────

class _EnsureRunningBase(unittest.TestCase):
    """Common harness: a fresh CrewLauncher plus patched lifecycle collaborators.

    ``ensure_running`` resolves ``_get_podman``, the gateway/cookie helpers, and
    the registry singleton lazily from ``transport.lifecycle`` /
    ``transport.registry`` at call time, so the harness patches those module
    attributes and seeds the registry.
    """

    def setUp(self):
        import transport.lifecycle as life
        import transport.registry as reg_mod
        from transport.launcher import CrewLauncher

        self.life = life
        self.reg_mod = reg_mod
        self.podman = FakePodmanClient()
        # A stopped crew container present in the fake.
        self.podman.add_container(CONTAINER, running=False)

        self.launcher = CrewLauncher(
            registry=reg_mod.registry, podman=self.podman, cfg=life.cfg,
        )

        self.crews = _patch_registry_backing(self, reg_mod, {
            CREW_ID: {
                "container": CONTAINER,
                "volume": "gs-vol-test",
                "home_volume": "gs-home-test",
                "cookie": "old-cookie",
                "status": "stopped",
            },
        })

        # Patch lifecycle collaborators. ensure_running imports these by name
        # from transport.lifecycle, so patch.object on the module is sufficient.
        self._patchers = [
            patch.object(life, "_get_podman", return_value=self.podman),
            patch.object(life, "_wait_gateway", return_value=True),
            patch.object(life, "_probe_gateway", return_value=True),
            patch.object(life, "_mint_cookie", return_value="test-cookie"),
            patch.object(life, "_mint_internal_cookie", return_value="int-cookie"),
            patch.object(life, "_patch_crew_config"),
            patch.object(life, "_deployed_agent_names", return_value=[]),
            patch.object(life, "_enroll_crew_members"),
            patch.object(life, "_write_dashboard_cookie"),
            patch.object(reg_mod, "_touch_crew"),
        ]
        for p in self._patchers:
            p.start()
        self.addCleanup(self._stop_all)

    def _stop_all(self):
        for p in self._patchers:
            p.stop()


# ── TestRestartKeepsBackend (TRN-259) ─────────────────────────────────────────

class TestRestartKeepsBackend(_EnsureRunningBase):
    """Restarts re-patch the crew config from the recorded acp_backend, not the
    transport default."""

    def _patched_backend(self):
        _args, kwargs = self.life._patch_crew_config.call_args
        return kwargs["backend"]

    def test_ensure_running_kiro_crew_under_claude_default(self):
        self.crews[CREW_ID]["acp_backend"] = "kiro"
        with patch.object(self.life, "GA_CREW_ACP_BACKEND", "claude"):
            self.launcher.ensure_running(dict(self.crews[CREW_ID]), CREW_ID)
        self.assertEqual(self._patched_backend(), "kiro")

    def test_ensure_running_claude_crew_under_kiro_default(self):
        self.crews[CREW_ID]["acp_backend"] = "claude"
        with patch.object(self.life, "GA_CREW_ACP_BACKEND", "kiro"):
            self.launcher.ensure_running(dict(self.crews[CREW_ID]), CREW_ID)
        self.assertEqual(self._patched_backend(), "claude")

    def test_ensure_running_missing_backend_is_kiro(self):
        self.crews[CREW_ID].pop("acp_backend", None)
        with patch.object(self.life, "GA_CREW_ACP_BACKEND", "claude"):
            self.launcher.ensure_running(dict(self.crews[CREW_ID]), CREW_ID)
        self.assertEqual(self._patched_backend(), "kiro")

    def test_reconcile_restart_cycle_uses_recorded_backend(self):
        self.crews[CREW_ID]["acp_backend"] = "kiro"
        with patch.object(self.life, "GA_CREW_ACP_BACKEND", "claude"):
            self.launcher._run_restart_cycle(dict(self.crews[CREW_ID]), CREW_ID)
        self.assertEqual(self._patched_backend(), "kiro")


# ── TestEnsureRunning ─────────────────────────────────────────────────────────

class TestEnsureRunning(_EnsureRunningBase):
    """CrewLauncher.ensure_running: happy path + nuked-during-restart sentinel."""

    def test_stopped_crew_starts_and_returns_running_dict(self):
        crew = dict(self.crews[CREW_ID])
        result = self.launcher.ensure_running(crew, CREW_ID)
        self.assertTrue(self.podman.was_called("container_start"))
        self.assertEqual(result["cookie"], "test-cookie")
        self.assertEqual(self.crews[CREW_ID]["status"], "running")

    def test_running_crew_with_live_gateway_returns_immediately(self):
        # Container already running + gateway probe succeeds → no restart.
        self.podman.add_container(CONTAINER, running=True)
        self.crews[CREW_ID]["status"] = "running"
        crew = dict(self.crews[CREW_ID])
        result = self.launcher.ensure_running(crew, CREW_ID)
        self.assertFalse(self.podman.was_called("container_start"))
        self.assertIs(result, crew)

    def test_nuked_during_restart_returns_sentinel(self):
        # Remove the registry entry as a side effect of container_start so the
        # post-start "still registered?" check sees it gone.
        crew = dict(self.crews[CREW_ID])
        real_start = self.podman.container_start

        def _start_then_nuke(name):
            real_start(name)
            self.crews.pop(CREW_ID, None)
        self.podman.container_start = _start_then_nuke

        result = self.launcher.ensure_running(crew, CREW_ID)
        self.assertIs(result, self.life._NUKED_DURING_RESTART)


# ── TestEnsureRunningConcurrency ──────────────────────────────────────────────

class TestEnsureRunningConcurrency(_EnsureRunningBase):
    """Leader/waiter serialisation, generation counter, exception propagation."""

    def _run_threads(self, targets, timeout=10):
        threads = [threading.Thread(target=t) for t in targets]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=timeout)
            self.assertFalse(t.is_alive(), "thread did not finish within timeout")

    def test_concurrent_callers_start_container_once(self):
        results: list = []
        errors: list = []
        # The leader signals once it is inside container_start (so it has
        # already registered the in-progress startup event); the second caller
        # waits for that signal before entering, guaranteeing it takes the
        # waiter path. The leader then blocks briefly so the waiter is parked on
        # event.wait() before the leader finishes.
        leader_in_start = threading.Event()
        real_start = self.podman.container_start

        def _slow_start(name):
            leader_in_start.set()
            # Hold long enough for the waiter to enter and block.
            __import__("time").sleep(0.3)
            real_start(name)
        self.podman.container_start = _slow_start

        def _leader():
            try:
                crew = dict(self.crews[CREW_ID])
                results.append(self.launcher.ensure_running(crew, CREW_ID))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        def _waiter():
            # Wait until the leader is mid-restart, then enter.
            leader_in_start.wait(timeout=5)
            try:
                crew = dict(self.crews[CREW_ID])
                results.append(self.launcher.ensure_running(crew, CREW_ID))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        self._run_threads([_leader, _waiter])

        self.assertEqual(errors, [], f"unexpected errors: {errors}")
        # Exactly one restart CYCLE ran: the leader's restart body calls
        # _patch_crew_config exactly once and waiters never call it, so a single
        # call proves only one caller did the work (the real restart body calls
        # container_start twice — initial start + post-config-repatch restart —
        # so counting container_start calls would not isolate the leader).
        self.assertEqual(self.life._patch_crew_config.call_count, 1)
        self.assertIn("backend", self.life._patch_crew_config.call_args.kwargs)
        self.assertEqual(len(results), 2)
        # Both callers returned a crew dict (neither the nuked sentinel). The
        # authoritative status lives in the registry — the leader's returned
        # dict carries the refreshed cookie but not an updated status field.
        for r in results:
            self.assertIsInstance(r, dict)
        self.assertEqual(self.crews[CREW_ID]["status"], "running")

    def test_leader_exception_propagates_to_waiters(self):
        errors: list = []
        leader_in_start = threading.Event()

        def _failing_start(name):
            leader_in_start.set()
            __import__("time").sleep(0.3)
            self.podman.calls.append(("container_start", name))
            raise RuntimeError("start failed")
        self.podman.container_start = _failing_start

        def _leader():
            try:
                crew = dict(self.crews[CREW_ID])
                self.launcher.ensure_running(crew, CREW_ID)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        def _waiter():
            leader_in_start.wait(timeout=5)
            try:
                crew = dict(self.crews[CREW_ID])
                self.launcher.ensure_running(crew, CREW_ID)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        self._run_threads([_leader, _waiter])

        self.assertEqual(len(errors), 2, f"expected both to raise, got {errors}")
        for exc in errors:
            self.assertIsInstance(exc, RuntimeError)
            self.assertIn("start failed", str(exc))

    def test_generation_change_raises_in_waiter(self):
        # Simulate a waiter that wakes to find a newer restart cycle running:
        # the generation counter advanced past the one the waiter captured.
        errors: list = []

        # Elect a leader-in-progress state by hand so the next caller is a
        # waiter: register an already-set event and a stale outcome, then bump
        # the generation after the waiter captures the old one.
        ev = threading.Event()
        self.launcher._startup_events[CREW_ID] = ev
        self.launcher._startup_generation[CREW_ID] = 1
        self.launcher._crew_restart_outcomes[CREW_ID] = (True, None)

        def _advance_generation_then_release():
            # Represent a third caller starting a brand-new restart cycle: the
            # event the waiter is blocked on fires, but the generation has moved
            # on, so the waiter must detect the mismatch and raise.
            self.launcher._startup_generation[CREW_ID] = 2
            ev.set()

        def _waiter():
            try:
                crew = dict(self.crews[CREW_ID])
                self.launcher.ensure_running(crew, CREW_ID)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        t = threading.Thread(target=_waiter)
        t.start()
        # Give the waiter a moment to enter event.wait(), then advance + release.
        threading.Timer(0.2, _advance_generation_then_release).start()
        t.join(timeout=10)
        self.assertFalse(t.is_alive(), "waiter did not finish within timeout")

        self.assertEqual(len(errors), 1, f"expected one error, got {errors}")
        self.assertIsInstance(errors[0], RuntimeError)
        self.assertIn("gen", str(errors[0]).lower())

    def test_waiter_sees_nuked_crew_after_waking(self):
        # Spec scenario: waiter wakes after a successful leader restart but the
        # crew registry entry has been removed by a concurrent nuke() between
        # container_start and post-start setup.  The waiter path calls
        # _get_crew(crew_id); if it raises KeyError the waiter should return
        # _NUKED_DURING_RESTART rather than raising or returning stale data.
        results: list = []
        leader_in_start = threading.Event()
        real_start = self.podman.container_start

        def _slow_start(name):
            leader_in_start.set()
            __import__("time").sleep(0.3)
            real_start(name)
        self.podman.container_start = _slow_start

        def _leader():
            try:
                crew = dict(self.crews[CREW_ID])
                results.append(self.launcher.ensure_running(crew, CREW_ID))
            except Exception as exc:  # noqa: BLE001
                results.append(exc)

        def _waiter():
            # Enter after leader is mid-restart; then nuke the registry entry
            # before the waiter wakes, so _get_crew raises KeyError.
            leader_in_start.wait(timeout=5)
            # Remove the crew entry — the leader will finish and write outcome,
            # then the waiter wakes and tries _get_crew which should KeyError.
            self.crews.pop(CREW_ID, None)
            try:
                crew = dict({
                    "container": CONTAINER,
                    "volume": "gs-vol-test",
                    "home_volume": "gs-home-test",
                    "cookie": "old-cookie",
                    "status": "stopped",
                })
                results.append(self.launcher.ensure_running(crew, CREW_ID))
            except Exception as exc:  # noqa: BLE001
                results.append(exc)

        self._run_threads([_leader, _waiter])

        # The leader may return a dict or sentinel; the waiter must specifically
        # return _NUKED_DURING_RESTART because the registry was empty when it
        # looked up the crew after waking.
        nuked_results = [r for r in results if r is self.life._NUKED_DURING_RESTART]
        self.assertGreaterEqual(
            len(nuked_results), 1,
            f"expected at least one _NUKED_DURING_RESTART result; got {results!r}",
        )


# ── TestActiveLimit ───────────────────────────────────────────────────────────

class TestActiveLimit(unittest.TestCase):
    """CrewLauncher._check_active_limit: active-crew gate + stale correction."""

    def setUp(self):
        import transport.lifecycle as life
        import transport.registry as reg_mod
        from transport.launcher import CrewLauncher

        self.life = life
        self.reg_mod = reg_mod
        self.podman = FakePodmanClient()
        self.launcher = CrewLauncher(
            registry=reg_mod.registry, podman=self.podman, cfg=life.cfg,
        )

    def _seed(self, crews):
        return _patch_registry_backing(self, self.reg_mod, crews)

    def test_limit_exceeded_raises(self):
        self.podman.add_container("gs-other", running=True)
        self._seed({"other": {"container": "gs-other", "status": "running"}})
        with patch.object(self.life, "GA_MAX_ACTIVE_CREWS", 1):
            with self.assertRaises(RuntimeError) as ctx:
                self.launcher._check_active_limit(self.podman, "new")
        self.assertIn("limit", str(ctx.exception).lower())

    def test_limit_not_exceeded_does_not_raise(self):
        self.podman.add_container("gs-other", running=True)
        self._seed({"other": {"container": "gs-other", "status": "running"}})
        with patch.object(self.life, "GA_MAX_ACTIVE_CREWS", 2):
            self.launcher._check_active_limit(self.podman, "new")  # no raise

    def test_limit_disabled_zero_never_raises(self):
        self.podman.add_container("gs-a", running=True)
        self.podman.add_container("gs-b", running=True)
        self._seed({
            "a": {"container": "gs-a", "status": "running"},
            "b": {"container": "gs-b", "status": "running"},
        })
        with patch.object(self.life, "GA_MAX_ACTIVE_CREWS", 0):
            self.launcher._check_active_limit(self.podman, "new")  # no raise

    def test_stale_running_entry_corrected_to_stopped(self):
        # Registry says running, but the container is not actually running.
        self.podman.add_container("gs-stale", running=False)
        crews = self._seed({"stale": {"container": "gs-stale", "status": "running"}})
        with patch.object(self.life, "GA_MAX_ACTIVE_CREWS", 1):
            self.launcher._check_active_limit(self.podman, "new")  # no raise
        self.assertEqual(crews["stale"]["status"], "stopped")


# ── TestMemoryGate ────────────────────────────────────────────────────────────

class TestMemoryGate(unittest.TestCase):
    """CrewLauncher._check_memory_gate: memory gate blocking + disabled=0."""

    def setUp(self):
        import transport.lifecycle as life
        import transport.registry as reg_mod
        from transport.launcher import CrewLauncher

        self.life = life
        self.podman = FakePodmanClient()
        self.launcher = CrewLauncher(
            registry=reg_mod.registry, podman=self.podman, cfg=life.cfg,
        )

    def test_insufficient_memory_raises(self):
        with patch.object(self.life, "GA_MIN_FREE_MEM_GB", 4.0), \
             patch.object(self.life, "_wait_for_memory", return_value=2.0):
            with self.assertRaises(RuntimeError) as ctx:
                self.launcher._check_memory_gate(self.podman, CREW_ID)
        msg = str(ctx.exception).lower()
        self.assertTrue("memory" in msg or "gb" in msg,
                        f"message should mention memory requirement: {msg!r}")

    def test_sufficient_memory_does_not_raise(self):
        with patch.object(self.life, "GA_MIN_FREE_MEM_GB", 4.0), \
             patch.object(self.life, "_wait_for_memory", return_value=8.0):
            self.launcher._check_memory_gate(self.podman, CREW_ID)  # no raise

    def test_gate_disabled_zero_never_raises(self):
        with patch.object(self.life, "GA_MIN_FREE_MEM_GB", 0), \
             patch.object(self.life, "_wait_for_memory", return_value=0.0):
            self.launcher._check_memory_gate(self.podman, CREW_ID)  # no raise


# ── TestStateTransitions ──────────────────────────────────────────────────────

class TestStateTransitions(_EnsureRunningBase):
    """End-to-end state graph: launching→running, running→stopped,
    stopped→running, running→removed."""

    def test_launching_to_running(self):
        # Minimal stubbed path: a launching entry transitions to running with a
        # cookie once ensure_running completes the restart.
        self.crews[CREW_ID]["status"] = "launching"
        crew = dict(self.crews[CREW_ID])
        self.launcher.ensure_running(crew, CREW_ID)
        self.assertEqual(self.crews[CREW_ID]["status"], "running")
        self.assertTrue(self.crews[CREW_ID].get("cookie"))

    def test_running_to_stopped_via_cleanup(self):
        from transport.lifecycle import _cleanup_crew
        self.podman.add_container(CONTAINER, running=True)
        _cleanup_crew(self.podman, CONTAINER, "gs-vol-test", "gs-home-test")
        self.assertTrue(self.podman.was_called("container_stop"))
        self.assertTrue(self.podman.was_called("container_remove"))
        self.assertFalse(self.podman.container_exists(CONTAINER))

    def test_stopped_to_running_via_ensure_running(self):
        self.assertEqual(self.crews[CREW_ID]["status"], "stopped")
        crew = dict(self.crews[CREW_ID])
        self.launcher.ensure_running(crew, CREW_ID)
        self.assertEqual(self.crews[CREW_ID]["status"], "running")
        self.assertTrue(self.podman.container_is_running(CONTAINER))

    def test_running_to_removed_via_nuke_path(self):
        from transport.lifecycle import _cleanup_crew
        self.podman.add_container(CONTAINER, running=True)
        self.podman.volume_create("gs-vol-test")
        self.podman.volume_create("gs-home-test")
        _cleanup_crew(self.podman, CONTAINER, "gs-vol-test", "gs-home-test")
        self.assertFalse(self.podman.container_exists(CONTAINER))
        self.assertNotIn("gs-vol-test", self.podman._volumes)
        self.assertNotIn("gs-home-test", self.podman._volumes)


class TestModelPrecedence(unittest.TestCase):
    """TRN-257: per-backend model resolution in the transport.

    Covers each level of the precedence chain
      dispatch > backend_override > per-agent > backend_default > model.default > built-in
    that the transport is responsible for.

    The transport owns four of the six levels: the per-backend override (a hard
    patch, _resolve_backend_model_override) and the fallback default
    (_resolve_backend_default_model, which folds backend_default > model.default
    > built-in). The remaining two — dispatch(model=) and per-agent model — are
    applied by the gateway at/after the config layer and are asserted via the
    documented relationship (override beats per-agent; per-agent beats the
    default the transport writes).
    """

    def setUp(self):
        import transport.lifecycle as life

        self.life = life
        # Snapshot the module-level model config so each test restores it.
        self._saved_override = dict(life._KC_MODEL_BACKEND_OVERRIDE)
        self._saved_default = dict(life._KC_MODEL_BACKEND_DEFAULT)
        self._saved_global = life.KC_MODEL_DEFAULT

    def tearDown(self):
        self.life._KC_MODEL_BACKEND_OVERRIDE = self._saved_override
        self.life._KC_MODEL_BACKEND_DEFAULT = self._saved_default
        self.life.KC_MODEL_DEFAULT = self._saved_global

    def _set(self, overrides=None, defaults=None, global_default=""):
        self.life._KC_MODEL_BACKEND_OVERRIDE = {
            "kiro": "", "claude": "", "codex": "", **(overrides or {})
        }
        self.life._KC_MODEL_BACKEND_DEFAULT = {
            "kiro": "", "claude": "", "codex": "", **(defaults or {})
        }
        self.life.KC_MODEL_DEFAULT = global_default

    # ── backend override (highest operator-controlled level) ──────────────────

    def test_backend_override_returned_for_that_backend(self):
        self._set(overrides={"kiro": "claude-sonnet-4-5"})
        self.assertEqual(
            self.life._resolve_backend_model_override("kiro"), "claude-sonnet-4-5"
        )

    def test_backend_override_isolated_to_its_backend(self):
        # kiro override set — claude and codex are unaffected.
        self._set(overrides={"kiro": "claude-sonnet-4-5"})
        self.assertEqual(self.life._resolve_backend_model_override("claude"), "")
        self.assertEqual(self.life._resolve_backend_model_override("codex"), "")

    def test_no_override_returns_empty(self):
        self._set()
        self.assertEqual(self.life._resolve_backend_model_override("kiro"), "")

    # ── backend default > global default > built-in ───────────────────────────

    def test_backend_default_beats_global_default(self):
        self._set(defaults={"kiro": "qwen-dense"}, global_default="gemma")
        self.assertEqual(self.life._resolve_backend_default_model("kiro"), "qwen-dense")
        # A backend with no per-backend default falls back to the global one.
        self.assertEqual(self.life._resolve_backend_default_model("claude"), "gemma")

    def test_global_default_is_final_fallback(self):
        self._set(global_default="gemma")
        for backend in ("kiro", "claude", "codex"):
            self.assertEqual(
                self.life._resolve_backend_default_model(backend), "gemma"
            )

    def test_built_in_when_nothing_set(self):
        self._set()
        self.assertEqual(self.life._resolve_backend_default_model("kiro"), "")

    def test_override_and_default_are_independent_levels(self):
        # Override set, default unset: default resolution still returns the
        # fallback (override is a separate, higher level applied via patch).
        self._set(overrides={"kiro": "forced"}, global_default="fallback")
        self.assertEqual(self.life._resolve_backend_model_override("kiro"), "forced")
        self.assertEqual(
            self.life._resolve_backend_default_model("kiro"), "fallback"
        )

    def test_default_model_written_only_when_nonempty(self):
        # When the resolved fallback is empty, the transport must NOT write
        # agent.default_model (leaving KiroCrew's built-in intact). The
        # resolver returning "" is what the lifecycle guard keys on.
        self._set()
        self.assertEqual(self.life._resolve_backend_default_model("codex"), "")


if __name__ == "__main__":
    unittest.main()


# ── TestPatchFollowsCrewBackend (TRN-259) ─────────────────────────────────────

class _ExecRecorder:
    """Minimal podman stand-in that records container_exec argv."""

    def __init__(self):
        self.calls: list[list[str]] = []

    def container_exec(self, container, cmd):
        self.calls.append(cmd)
        return "ok"


class TestPatchFollowsCrewBackend(unittest.TestCase):
    """_patch_crew_config / _patch_models use the crew's backend, not the
    transport default."""

    def setUp(self):
        import transport.lifecycle as life
        self.life = life
        self._patchers = [
            patch.object(life, "GA_CREW_ACP_BACKEND", "claude"),
            patch.object(life, "_load_crew_manifest", return_value={}),
            patch.dict(life._KC_MODEL_BACKEND_OVERRIDE,
                       {"kiro": "kiro-override", "claude": "claude-override"}, clear=True),
            patch.dict(life._KC_MODEL_BACKEND_DEFAULT,
                       {"kiro": "kiro-default", "claude": "claude-default"}, clear=True),
        ]
        for p in self._patchers:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self._patchers])

    def _agent_overrides(self, backend):
        import base64
        import json
        rec = _ExecRecorder()
        self.life._patch_crew_config(rec, "gs-crew-x", backend=backend)
        return json.loads(base64.b64decode(rec.calls[-1][-1]))["agent"]

    def test_kiro_crew_under_claude_default(self):
        agent = self._agent_overrides("kiro")
        self.assertNotIn("acp_backend", agent)
        self.assertEqual(agent["default_model"], "kiro-default")

    def test_claude_crew(self):
        agent = self._agent_overrides("claude")
        self.assertEqual(agent["acp_backend"], "claude")
        self.assertEqual(agent["default_model"], "claude-default")

    def test_patch_models_uses_crew_backend(self):
        rec = _ExecRecorder()
        self.life._patch_models(rec, "gs-crew-x", backend="kiro")
        self.assertEqual(rec.calls[-1][-1], "kiro-override")

    def test_backend_is_required(self):
        with self.assertRaises(TypeError):
            self.life._patch_crew_config(_ExecRecorder(), "gs-crew-x")


# ---------------------------------------------------------------------------
# TRN-260 H-1: inject_policy uses stdin, not argv (secret-delivery-hardening)
# ---------------------------------------------------------------------------

class TestInjectPolicyStdinDelivery(unittest.TestCase):
    """Assert that _inject_policy delivers the signing key via stdin, not argv.

    H-1: passing the key as argv exposes it in /proc/<pid>/cmdline.
    The fix: container_exec_stdin is used and the key does NOT appear in argv.
    """

    def setUp(self):
        try:
            from lifecycle import _inject_policy  # container flat layout
        except ModuleNotFoundError:
            from transport.lifecycle import _inject_policy  # local dev
        self._inject_policy = _inject_policy

    def _make_podman(self):
        from tests.fakes import FakePodmanClient
        podman = FakePodmanClient()
        podman.exec_responses["test-container"] = "policy injected version=1"
        return podman

    def _patch_policy(self):
        """Mock Path.read_text so _inject_policy doesn't need /policies/default.json."""
        import json as _json
        _fake_policy = _json.dumps({"version": "1", "rules": []})
        return unittest.mock.patch(
            "pathlib.Path.read_text", return_value=_fake_policy
        )

    def test_uses_container_exec_stdin_not_exec_checked(self):
        """_inject_policy must call container_exec_stdin, not container_exec_checked."""
        podman = self._make_podman()
        with self._patch_policy():
            self._inject_policy(podman, "test-container", "spec-ops", "my-secret-key")
        call_types = [c[0] for c in podman.calls]
        self.assertIn("container_exec_stdin", call_types)
        self.assertNotIn("container_exec_checked", call_types)

    def test_signing_key_not_in_argv(self):
        """The policy signing key must not appear in any argv element."""
        secret = "super-secret-hmac-key-12345"
        podman = self._make_podman()
        with self._patch_policy():
            self._inject_policy(podman, "test-container", "spec-ops", secret)
        for call in podman.calls:
            if call[0] == "container_exec_stdin":
                cmd = call[2]  # (type, container, cmd, stdin_data)
                for arg in cmd:
                    self.assertNotIn(secret, arg,
                        f"Signing key found in argv element {arg!r}")

    def test_signing_key_delivered_via_stdin(self):
        """The signing key must be present in the decoded stdin payload."""
        import base64, json as _json
        secret = "super-secret-hmac-key-12345"
        podman = self._make_podman()
        with self._patch_policy():
            self._inject_policy(podman, "test-container", "spec-ops", secret)
        for call in podman.calls:
            if call[0] == "container_exec_stdin":
                stdin_data = call[3]
                decoded = base64.b64decode(stdin_data.strip()).decode()
                self.assertIn(secret, decoded,
                    "Signing key not found in decoded stdin payload")

    def test_payload_is_base64_json_with_key(self):
        """stdin_data must be base64-decodable JSON containing policy_signing_key."""
        import base64, json as _json
        secret = "another-secret-key"
        podman = self._make_podman()
        with self._patch_policy():
            self._inject_policy(podman, "test-container", "spec-ops", secret)
        for call in podman.calls:
            if call[0] == "container_exec_stdin":
                stdin_data = call[3]
                data = _json.loads(base64.b64decode(stdin_data.strip()).decode())
                self.assertEqual(data["policy_signing_key"], secret)
                self.assertIn("policy", data)


# ---------------------------------------------------------------------------
# TRN-269: inject_auth uses stdin, not argv (secret-delivery-hardening)
# ---------------------------------------------------------------------------

class TestInjectAuthStdin(unittest.TestCase):
    """Assert that _inject_auth delivers the auth payload via stdin, not argv.

    TRN-269: passing auth_b64 as argv exposes it in /proc/<pid>/cmdline.
    The fix: container_exec_stdin is used and auth_b64 does NOT appear in argv.
    Mirrors the structure of TestInjectPolicyStdinDelivery (TRN-260 H-1).
    """

    def setUp(self):
        try:
            from lifecycle import _inject_auth  # container flat layout
        except ModuleNotFoundError:
            from transport.lifecycle import _inject_auth  # local dev
        self._inject_auth = _inject_auth

    def _make_podman(self):
        from tests.fakes import FakePodmanClient
        podman = FakePodmanClient()
        podman.exec_responses["test-container"] = "injected 2 auth rows"
        return podman

    def test_uses_container_exec_stdin_not_exec_checked(self):
        """_inject_auth must call container_exec_stdin, not container_exec_checked."""
        import base64 as _b64, json as _json
        auth_b64 = _b64.b64encode(_json.dumps([["key1", "val1"]]).encode()).decode()
        podman = self._make_podman()
        self._inject_auth(podman, "test-container", auth_b64)
        call_types = [c[0] for c in podman.calls]
        self.assertIn("container_exec_stdin", call_types)
        self.assertNotIn("container_exec_checked", call_types)

    def test_auth_b64_not_in_argv(self):
        """The auth payload must not appear in any argv element."""
        import base64 as _b64, json as _json
        auth_b64 = _b64.b64encode(_json.dumps([["key1", "val1"]]).encode()).decode()
        podman = self._make_podman()
        self._inject_auth(podman, "test-container", auth_b64)
        for call in podman.calls:
            if call[0] == "container_exec_stdin":
                cmd = call[2]  # (type, container, cmd, stdin_data)
                for arg in cmd:
                    self.assertNotIn(auth_b64, arg,
                        f"auth_b64 found in argv element {arg!r}")

    def test_auth_b64_delivered_via_stdin(self):
        """The auth payload must be present in the stdin_data bytes."""
        import base64 as _b64, json as _json
        auth_b64 = _b64.b64encode(_json.dumps([["key1", "val1"]]).encode()).decode()
        podman = self._make_podman()
        self._inject_auth(podman, "test-container", auth_b64)
        for call in podman.calls:
            if call[0] == "container_exec_stdin":
                stdin_data = call[3]
                self.assertIn(auth_b64.encode("utf-8"), stdin_data,
                    "auth_b64 not found in stdin_data bytes")
