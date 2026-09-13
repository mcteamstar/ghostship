"""Unit tests: generation-counter race fix + Admiral keypair TOCTOU fix.

CR-1: Three-caller generation-counter tests — exercise the _startup_generation
      mechanism added to _ensure_crew_running.
CR-2: Admiral keypair TOCTOU tests — exercise the _cleanup_crew call on
      _finish_crew_setup cookie-mint failure and the registry cleanup in launch().
"""

from __future__ import annotations

import threading
import unittest
from unittest.mock import Mock, patch, call

from tests.unit.helpers import server, lifecycle


# ── Shared helpers ────────────────────────────────────────────────────────────


def _make_running_crew(container: str = "gs-test") -> dict:
    return {"status": "running", "container": container, "cookie": "c"}


def _make_stopped_crew(container: str = "gs-test") -> dict:
    return {"status": "stopped", "container": container, "cookie": "c"}


# ── CR-1: generation-counter race tests ──────────────────────────────────────


class GenerationCounterTests(unittest.TestCase):
    """Tests for the generation-counter fix in _ensure_crew_running."""

    def test_three_caller_generation_check_raises(self) -> None:
        """Waiter wakes to find generation has advanced (third caller took over) —
        must raise RuntimeError with the generation mismatch message rather than a
        spurious 'leader did not record an outcome' error."""
        crew_id = "gen-race"

        # Simulate: leader A fired the event and set outcome; then leader C
        # incremented the generation (new cycle). Waiter B woke up, captures
        # gen=2 from _startup_generation, but had captured gen=1 before wait().
        event = threading.Event()
        event.set()  # already fired — waiter will return immediately from wait()

        startup_events = {crew_id: event}
        # gen=2: leader C already started a new cycle while waiter was sleeping
        startup_generation = {crew_id: 2}
        # outcome from leader A (previous cycle) — should NOT be read
        crew_restart_outcomes = {crew_id: (True, None)}

        # The waiter captures gen=1 (before wait) but sees gen=2 after waking
        # We simulate this by patching the generation dict to return 1 on the
        # first get() and 2 on the second.  Easier: patch _startup_generation
        # so waiter captures gen=1 inside the election lock, then sees gen=2
        # when it re-acquires to read the outcome.
        #
        # The code captures `_waiter_gen = _startup_generation.get(crew_id, 0)`
        # inside `with _startup_events_lock` (election branch `is_leader=False`),
        # and then reads `_current_gen = _startup_generation.get(crew_id, 0)`
        # inside a second lock acquisition after event.wait().
        #
        # Strategy: start with gen=1, then bump to gen=2 after event.wait()
        # returns. We use a threading.Event to synchronise the bump.

        # A real threading test: run the waiter in a thread.
        generation_dict = {crew_id: 1}  # waiter captures gen=1 at election
        startup_generation_initial = {crew_id: 1}

        bump_done = threading.Event()

        def bump_generation() -> None:
            # Bump generation AFTER the waiter has already captured _waiter_gen=1
            # and returned from event.wait() but before it re-acquires the lock.
            # We advance gen to 2 here.
            generation_dict[crew_id] = 2
            bump_done.set()

        # Use a custom event that bumps the generation when it returns True
        class BumpOnWaitEvent:
            def set(self) -> None:
                pass

            def wait(self, timeout: float | None = None) -> bool:
                # Before returning, advance the generation (simulating C)
                generation_dict[crew_id] = 2
                return True

        bump_event = BumpOnWaitEvent()
        startup_events_bump = {crew_id: bump_event}

        crew = _make_stopped_crew()

        with (
            patch.object(lifecycle, "_startup_events", startup_events_bump),
            patch.object(lifecycle, "_startup_events_lock", threading.Lock()),
            patch.object(lifecycle, "_startup_generation", generation_dict),
            patch.object(lifecycle, "_crew_restart_outcomes", {crew_id: (True, None)}),
            patch.object(lifecycle, "_get_podman", return_value=Mock()),
            patch.object(lifecycle, "GA_MAX_ACTIVE_CREWS", 0),
            patch.object(lifecycle, "GA_MIN_FREE_MEM_GB", 0.0),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                server._ensure_crew_running(crew, crew_id)

        msg = str(ctx.exception)
        self.assertIn("restart cycle changed", msg)
        self.assertIn("waited on gen 1", msg)
        self.assertIn("current gen 2", msg)
        # Must NOT say "leader did not record an outcome" — wrong error for this case
        self.assertNotIn("leader did not record an outcome", msg)

    def test_two_caller_normal_case_unaffected(self) -> None:
        """Normal two-caller case: gen is stable between capture and outcome read.
        Waiter should read outcome (True, None) and proceed without error."""
        crew_id = "gen-normal"

        # The leader fires and records success; gen stays at 1 throughout.
        event = threading.Event()
        event.set()

        startup_events = {crew_id: event}
        # gen=1, consistent
        startup_generation = {crew_id: 1}
        # Waiter captures gen=1 inside election (is_leader=False branch)
        # After event.wait(), reads gen=1 again — match, no raise.
        crew_restart_outcomes = {crew_id: (True, None)}

        crew = _make_stopped_crew()

        with (
            patch.object(lifecycle, "_startup_events", startup_events),
            patch.object(lifecycle, "_startup_events_lock", threading.Lock()),
            patch.object(lifecycle, "_startup_generation", dict(startup_generation)),
            patch.object(lifecycle, "_crew_restart_outcomes", dict(crew_restart_outcomes)),
            patch.object(lifecycle, "_get_podman", return_value=Mock()),
            patch.object(lifecycle, "GA_MAX_ACTIVE_CREWS", 0),
            patch.object(lifecycle, "GA_MIN_FREE_MEM_GB", 0.0),
            patch.object(lifecycle, "_get_crew", return_value={"status": "running", "container": "gs-test", "cookie": "c"}),
        ):
            result = server._ensure_crew_running(crew, crew_id)

        # Should return the refreshed crew without raising
        self.assertIsNotNone(result)
        self.assertEqual(result.get("status"), "running")

    def test_leader_failure_propagated_to_waiter(self) -> None:
        """Leader fails; gen unchanged. Waiter should re-raise the stored exception."""
        crew_id = "gen-leader-fail"

        event = threading.Event()
        event.set()

        class _TestError(RuntimeError):
            pass

        stored_exc = _TestError("leader had a bad day")
        startup_events = {crew_id: event}
        startup_generation = {crew_id: 1}
        crew_restart_outcomes = {crew_id: (False, stored_exc)}

        crew = _make_stopped_crew()

        with (
            patch.object(lifecycle, "_startup_events", startup_events),
            patch.object(lifecycle, "_startup_events_lock", threading.Lock()),
            patch.object(lifecycle, "_startup_generation", dict(startup_generation)),
            patch.object(lifecycle, "_crew_restart_outcomes", dict(crew_restart_outcomes)),
            patch.object(lifecycle, "_get_podman", return_value=Mock()),
            patch.object(lifecycle, "GA_MAX_ACTIVE_CREWS", 0),
            patch.object(lifecycle, "GA_MIN_FREE_MEM_GB", 0.0),
        ):
            with self.assertRaises(_TestError) as ctx:
                server._ensure_crew_running(crew, crew_id)

        self.assertIs(ctx.exception, stored_exc)

    def test_leader_increments_generation(self) -> None:
        """When a new leader is elected, _startup_generation[crew_id] is incremented."""
        crew_id = "gen-increment"

        generation_dict: dict[str, int] = {}  # starts empty

        class ImmediateErrorPodman:
            def container_is_running(self, name: str) -> bool:
                return False

            def container_start(self, name: str) -> None:
                pass

            def container_stop(self, name: str) -> None:
                pass

        with (
            patch.object(lifecycle, "_startup_events", {}),
            patch.object(lifecycle, "_startup_events_lock", threading.Lock()),
            patch.object(lifecycle, "_startup_generation", generation_dict),
            patch.object(lifecycle, "_crew_restart_outcomes", {}),
            patch.object(lifecycle, "_get_podman", return_value=ImmediateErrorPodman()),
            patch.object(lifecycle, "GA_MAX_ACTIVE_CREWS", 0),
            patch.object(lifecycle, "GA_MIN_FREE_MEM_GB", 0.0),
            patch.object(lifecycle, "_wait_gateway", side_effect=RuntimeError("boom")),
        ):
            with self.assertRaises(RuntimeError):
                server._ensure_crew_running(_make_stopped_crew(), crew_id)

        # Generation must have been incremented from 0 → 1
        self.assertEqual(generation_dict.get(crew_id, 0), 1)


# ── CR-2: Admiral keypair TOCTOU tests ────────────────────────────────────────


class FinishCrewSetupCookieCleanupTests(unittest.TestCase):
    """Tests for CR-2: _cleanup_crew called on cookie-mint failure."""

    def test_finish_crew_setup_cookie_failure_calls_cleanup(self) -> None:
        """When _mint_cookie returns None, _cleanup_crew is called and
        _finish_crew_setup returns an error dict."""
        cleanup_calls: list = []

        def fake_cleanup(podman, container, volume, home_volume) -> None:
            cleanup_calls.append((container, volume, home_volume))

        podman = Mock()
        podman.container_exec.return_value = "ready"

        with (
            patch.object(lifecycle, "_wait_gateway", return_value=True),
            patch.object(lifecycle, "KIRO_API_KEY", ""),
            patch.object(lifecycle, "_inject_auth"),
            patch.object(lifecycle, "_patch_crew_config"),
            patch.object(lifecycle, "_copy_agents"),
            patch.object(lifecycle, "_copy_skills"),
            patch.object(lifecycle, "_copy_steering"),
            patch.object(lifecycle, "_seed_openspec_store"),
            patch.object(lifecycle, "_inject_policy", return_value="v1"),
            patch.object(lifecycle, "_patch_models"),
            patch.object(lifecycle, "_mint_cookie", return_value=None),
            patch.object(lifecycle, "_cleanup_crew", side_effect=fake_cleanup),
        ):
            result = lifecycle._finish_crew_setup(
                podman,
                "test-crew",
                "gs-test-crew",
                "vol-test-crew",
                "home-vol-test-crew",
                "auth-b64",
                admiral_secret="deadbeef" * 8,
            )

        self.assertIn("error", result)
        self.assertIn("Failed to mint session cookie", result["error"])
        self.assertEqual(len(cleanup_calls), 1)
        self.assertEqual(cleanup_calls[0][0], "gs-test-crew")
        self.assertEqual(cleanup_calls[0][1], "vol-test-crew")
        self.assertEqual(cleanup_calls[0][2], "home-vol-test-crew")


class LaunchRegistryCleanupOnErrorDictTests(unittest.TestCase):
    """Tests for CR-2: launch() cleans up registry when
    _finish_crew_setup returns an error dict."""

    def _build_launch_patches(
        self,
        *,
        finish_result: dict,
        dashboard_port: int | None = None,
    ):
        """Build a context manager stack that drives launch() to the
        _finish_crew_setup call with a scripted result."""
        import contextlib

        registry: dict = {"crews": {}}
        saved: list[dict] = []

        def fake_save(reg: dict) -> None:
            import copy
            saved.append(copy.deepcopy(reg))

        podman = Mock()
        caddy_portal = Mock()
        caddy_portal.allocate_port.return_value = dashboard_port or 9000
        caddy_portal.release_port = Mock()

        stack = contextlib.ExitStack()
        stack.enter_context(patch.object(server, "KIRO_API_KEY", "test-key"))
        stack.enter_context(patch.object(server, "_get_podman", return_value=podman))
        stack.enter_context(patch.object(lifecycle, "_get_podman", return_value=podman))
        stack.enter_context(patch.object(server, "_read_auth_file", return_value=""))
        stack.enter_context(patch.object(server, "_load_registry", return_value=registry))
        stack.enter_context(patch.object(lifecycle, "_load_registry", return_value=registry))
        stack.enter_context(patch.object(server, "_save_registry", side_effect=fake_save))
        stack.enter_context(patch.object(lifecycle, "_save_registry", side_effect=fake_save))
        stack.enter_context(patch.object(server, "_wait_gateway", return_value=True))
        stack.enter_context(patch.object(server, "_finish_crew_setup",
                                          return_value=finish_result))
        stack.enter_context(patch.object(server, "_write_crew_secret"))
        stack.enter_context(patch.object(server, "_caddy_portal", caddy_portal))

        return stack, registry, saved, caddy_portal

    def test_launch_cleans_registry_on_finish_crew_setup_error_dict(self) -> None:
        """When _finish_crew_setup returns {"error": ...}, launch() removes the
        placeholder entry from the registry and returns the error dict."""
        finish_result = {"error": "Gateway did not recover after auth restart for crew trn157-crew"}
        stack, registry, saved, caddy_portal = self._build_launch_patches(
            finish_result=finish_result,
            dashboard_port=None,
        )
        with stack:
            result = server.launch("trn157-crew")

        self.assertIn("error", result)
        # The final saved registry state must not contain the crew entry
        # (the cleanup pop must have run)
        if saved:
            final_reg = saved[-1]
            self.assertNotIn("trn157-crew", final_reg.get("crews", {}))

    def test_launch_cleans_registry_and_releases_port_on_error_dict(self) -> None:
        """When _finish_crew_setup returns an error dict AND a dashboard port was
        allocated, launch() must release that port."""
        finish_result = {"error": "Failed to mint session cookie for crew trn157-port-crew"}

        stack, registry, saved, caddy_portal = self._build_launch_patches(
            finish_result=finish_result,
            dashboard_port=9042,
        )
        # Force effective_dashboard=True so a port is allocated
        stack.enter_context(patch.object(server, "cfg", Mock(
            ga_dashboard_default=True,
            ga_host_url=None,
            ga_portal_tls_mode="off",
        )))
        # caddy_portal must be patched in the server namespace as a real attribute
        with stack:
            result = server.launch("trn157-port-crew")

        self.assertIn("error", result)
        caddy_portal.release_port.assert_called_once()

    def test_launch_error_dict_does_not_proceed_to_caddy_register(self) -> None:
        """When _finish_crew_setup returns an error dict, launch must NOT attempt
        to register the crew with Caddy (which would panic on missing fields)."""
        finish_result = {"error": "test error"}

        stack, registry, saved, caddy_portal = self._build_launch_patches(
            finish_result=finish_result,
            dashboard_port=None,
        )
        with stack:
            server.launch("trn157-nocaddy-crew")

        caddy_portal.register_crew.assert_not_called()


class NoOrphanedAdmiralSecretTests(unittest.TestCase):
    """Integration-style test: no orphaned admiral secret after failed launch."""

    def test_no_orphaned_admiral_secret_after_cookie_failure(self) -> None:
        """When _mint_cookie fails in _finish_crew_setup, _cleanup_crew is called,
        which should include secret_remove. This wires _cleanup_crew → podman to
        verify that the cleanup function is actually called."""
        crew_id = "trn157-secret-cleanup"
        cleanup_called = threading.Event()
        cleanup_args: list = []

        original_cleanup = lifecycle._cleanup_crew

        def tracking_cleanup(podman, container, volume, home_volume) -> None:
            cleanup_args.extend([container, volume, home_volume])
            cleanup_called.set()
            # Don't call real cleanup to avoid side effects

        with (
            patch.object(lifecycle, "_wait_gateway", return_value=True),
            patch.object(lifecycle, "KIRO_API_KEY", ""),
            patch.object(lifecycle, "_inject_auth"),
            patch.object(lifecycle, "_patch_crew_config"),
            patch.object(lifecycle, "_copy_agents"),
            patch.object(lifecycle, "_copy_skills"),
            patch.object(lifecycle, "_copy_steering"),
            patch.object(lifecycle, "_seed_openspec_store"),
            patch.object(lifecycle, "_inject_policy", return_value="v1"),
            patch.object(lifecycle, "_patch_models"),
            patch.object(lifecycle, "_mint_cookie", return_value=None),
            patch.object(lifecycle, "_cleanup_crew", side_effect=tracking_cleanup),
        ):
            podman = Mock()
            podman.container_exec.return_value = "ready"
            result = lifecycle._finish_crew_setup(
                podman,
                crew_id,
                f"gs-{crew_id}",
                f"vol-{crew_id}",
                f"home-{crew_id}",
                "auth",
                admiral_secret="aa" * 32,
            )

        self.assertTrue(cleanup_called.is_set(),
                        "_cleanup_crew was not called after cookie-mint failure")
        self.assertIn("error", result)
        # Cleanup received the correct container/volume arguments
        self.assertIn(f"gs-{crew_id}", cleanup_args)
        self.assertIn(f"vol-{crew_id}", cleanup_args)
        self.assertIn(f"home-{crew_id}", cleanup_args)


if __name__ == "__main__":
    unittest.main()
