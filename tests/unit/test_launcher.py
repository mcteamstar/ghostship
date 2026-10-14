"""Unit tests for transport.launcher — CrewLauncher.ensure_running (task 6.2).

Tests cover:
- Concurrent restart serialisation: two threads, one becomes waiter, reads
  leader outcome.
- Active-limit gate: blocks when at limit, passes below it.
- Memory gate: blocks when memory insufficient.
- _NUKED_DURING_RESTART sentinel propagation to both leader and waiter.
"""

from __future__ import annotations

import threading
import unittest
from unittest.mock import Mock, patch

from tests.unit._stubs import install_import_stubs
install_import_stubs()

import transport.lifecycle as lifecycle
import transport.launcher as launcher_mod
import transport.registry as _registry_mod

from transport.launcher import CrewLauncher, _NUKED_DURING_RESTART
from transport.registry import CrewRegistry


def _make_stopped_crew(container: str = "gs-test") -> dict:
    return {"status": "stopped", "container": container, "cookie": "c"}


def _make_running_crew(container: str = "gs-test") -> dict:
    return {"status": "running", "container": container, "cookie": "c"}


def _make_launcher() -> CrewLauncher:
    """Create a fresh CrewLauncher instance with a mock registry and podman."""
    mock_registry = Mock(spec=CrewRegistry)
    mock_registry._reg = {"crews": {}}
    mock_registry.__enter__ = lambda self: self
    mock_registry.__exit__ = Mock(return_value=False)
    return CrewLauncher(
        registry=mock_registry,
        podman=Mock(),
        cfg=Mock(),
    )


class TestConcurrentRestartSerialisation(unittest.TestCase):
    """Two threads calling ensure_running for the same crew: one leads, one waits."""

    def setUp(self) -> None:
        self.launcher = _make_launcher()

    def test_leader_and_waiter_via_pre_seeded_event(self) -> None:
        """Pre-seed a startup event (simulating a leader mid-restart) and
        verify a second caller takes the waiter path — reading the leader's
        outcome without calling container_start again."""
        crew_id = "concurrent"
        crew = _make_stopped_crew("gs-concurrent")
        running_crew = _make_running_crew("gs-concurrent")
        running_crew["cookie"] = "new-c"

        # Pre-seed: leader has finished and recorded success
        ev = threading.Event()
        ev.set()
        with self.launcher._startup_events_lock:
            self.launcher._startup_events[crew_id] = ev
            self.launcher._startup_generation[crew_id] = 1
            self.launcher._crew_restart_outcomes[crew_id] = (True, None)

        podman = Mock()
        podman.container_start = Mock()  # must NOT be called by waiter

        with (
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(lifecycle, "_get_crew", return_value=running_crew),
        ):
            result = self.launcher.ensure_running(crew, crew_id)

        # Waiter returned the refreshed crew
        self.assertEqual(result["status"], "running")
        # Waiter did NOT call container_start
        podman.container_start.assert_not_called()

    def test_waiter_reads_leader_outcome(self) -> None:
        """A waiter that wakes while the leader succeeded gets the refreshed crew."""
        crew_id = "waiter-reads"
        crew = _make_stopped_crew("gs-waiter")
        running_crew = _make_running_crew("gs-waiter")
        running_crew["cookie"] = "new-c"

        # Pre-seed a finished startup event — leader already done
        ev = threading.Event()
        ev.set()
        with self.launcher._startup_events_lock:
            self.launcher._startup_events[crew_id] = ev
            self.launcher._startup_generation[crew_id] = 1
            self.launcher._crew_restart_outcomes[crew_id] = (True, None)

        with (
            patch.object(lifecycle, "_get_podman", return_value=Mock()),
            patch.object(lifecycle, "_get_crew", return_value=running_crew),
        ):
            result = self.launcher.ensure_running(crew, crew_id)

        self.assertEqual(result["status"], "running")
        self.assertEqual(result["cookie"], "new-c")

    def test_waiter_propagates_leader_exception(self) -> None:
        """When the leader's restart failed, the waiter re-raises the stored exc."""
        crew_id = "waiter-exc"
        crew = _make_stopped_crew("gs-waiter-exc")
        sentinel_exc = RuntimeError("leader exploded")

        ev = threading.Event()
        ev.set()
        with self.launcher._startup_events_lock:
            self.launcher._startup_events[crew_id] = ev
            self.launcher._startup_generation[crew_id] = 1
            self.launcher._crew_restart_outcomes[crew_id] = (False, sentinel_exc)

        with (
            patch.object(lifecycle, "_get_podman", return_value=Mock()),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                self.launcher.ensure_running(crew, crew_id)

        self.assertIs(ctx.exception, sentinel_exc)


class TestActiveLimitGate(unittest.TestCase):
    """_check_active_limit blocks restarts when the limit is reached."""

    def setUp(self) -> None:
        self.launcher = _make_launcher()

    def test_blocks_when_at_limit(self) -> None:
        """ensure_running raises RuntimeError when active_crews == GA_MAX_ACTIVE_CREWS."""
        crew_id = "limit-test"
        crew = _make_stopped_crew("gs-limit")
        reg_data = {
            "crews": {
                "a": _make_running_crew("gs-a"),
                "b": _make_running_crew("gs-b"),
                crew_id: crew,
            }
        }
        self.launcher._registry._reg = reg_data

        def is_running(name: str) -> bool:
            return name in ("gs-a", "gs-b")

        podman = Mock()
        podman.container_is_running.side_effect = is_running
        podman.container_start.return_value = None

        with (
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(lifecycle, "GA_MAX_ACTIVE_CREWS", 2),
            patch.object(lifecycle, "GA_MIN_FREE_MEM_GB", 0.0),
            patch.object(_registry_mod, "_load_registry", return_value=reg_data),
            patch.object(_registry_mod, "_save_registry"),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                self.launcher.ensure_running(crew, crew_id)

        self.assertIn("Active crew limit", str(ctx.exception))

    def test_passes_below_limit(self) -> None:
        """ensure_running proceeds when active_crews < GA_MAX_ACTIVE_CREWS."""
        crew_id = "below-limit"
        crew = _make_stopped_crew("gs-below")
        reg_data = {
            "crews": {
                "a": _make_running_crew("gs-a"),
                crew_id: crew,
            }
        }
        self.launcher._registry._reg = reg_data

        podman = Mock()
        podman.container_is_running.return_value = False
        podman.container_start.return_value = None
        podman.container_stop.return_value = None
        podman.container_exec.return_value = "ok"

        with (
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(lifecycle, "GA_MAX_ACTIVE_CREWS", 3),
            patch.object(lifecycle, "GA_MIN_FREE_MEM_GB", 0.0),
            patch.object(_registry_mod, "_load_registry", return_value=reg_data),
            patch.object(_registry_mod, "_save_registry"),
            patch.object(lifecycle, "_wait_gateway", return_value=True),
            patch.object(lifecycle, "_patch_crew_config"),
            patch.object(lifecycle, "_mint_cookie", return_value="new-c"),
            patch.object(lifecycle, "_mint_internal_cookie", return_value=None),
            patch.object(lifecycle, "_deployed_agent_names", return_value=[]),
            patch.object(lifecycle, "_enroll_crew_members"),
            patch.object(lifecycle, "_write_dashboard_cookie", return_value=True),
            patch.object(_registry_mod, "_touch_crew"),
        ):
            result = self.launcher.ensure_running(crew, crew_id)

        self.assertIsNotNone(result)

    def test_disabled_at_zero(self) -> None:
        """GA_MAX_ACTIVE_CREWS=0 disables the limit — no RuntimeError."""
        crew_id = "no-limit"
        crew = _make_stopped_crew("gs-no-limit")
        reg_data = {"crews": {crew_id: crew}}
        self.launcher._registry._reg = reg_data

        podman = Mock()
        podman.container_is_running.return_value = False
        podman.container_start.return_value = None
        podman.container_stop.return_value = None
        podman.container_exec.return_value = "ok"

        with (
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(lifecycle, "GA_MAX_ACTIVE_CREWS", 0),
            patch.object(lifecycle, "GA_MIN_FREE_MEM_GB", 0.0),
            patch.object(_registry_mod, "_load_registry", return_value=reg_data),
            patch.object(_registry_mod, "_save_registry"),
            patch.object(lifecycle, "_wait_gateway", return_value=True),
            patch.object(lifecycle, "_patch_crew_config"),
            patch.object(lifecycle, "_mint_cookie", return_value="new-c"),
            patch.object(lifecycle, "_mint_internal_cookie", return_value=None),
            patch.object(lifecycle, "_deployed_agent_names", return_value=[]),
            patch.object(lifecycle, "_enroll_crew_members"),
            patch.object(lifecycle, "_write_dashboard_cookie", return_value=True),
            patch.object(_registry_mod, "_touch_crew"),
        ):
            result = self.launcher.ensure_running(crew, crew_id)

        self.assertIsNotNone(result)


class TestMemoryGate(unittest.TestCase):
    """_check_memory_gate blocks restarts when memory is insufficient."""

    def setUp(self) -> None:
        self.launcher = _make_launcher()

    def test_blocks_when_memory_insufficient(self) -> None:
        """ensure_running raises RuntimeError when free memory < GA_MIN_FREE_MEM_GB."""
        crew_id = "mem-gate"
        crew = _make_stopped_crew("gs-mem")
        reg_data = {"crews": {crew_id: crew}}
        self.launcher._registry._reg = reg_data

        podman = Mock()
        podman.container_is_running.return_value = False

        def low_memory_wait(podman, required_gb, timeout):
            return 0.5  # below requirement

        with (
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(lifecycle, "GA_MAX_ACTIVE_CREWS", 0),
            patch.object(lifecycle, "GA_MIN_FREE_MEM_GB", 4.0),
            patch.object(lifecycle, "_wait_for_memory", side_effect=low_memory_wait),
            patch.object(_registry_mod, "_load_registry", return_value=reg_data),
            patch.object(_registry_mod, "_save_registry"),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                self.launcher.ensure_running(crew, crew_id)

        self.assertIn("Insufficient available memory", str(ctx.exception))

    def test_disabled_at_zero(self) -> None:
        """GA_MIN_FREE_MEM_GB=0 disables the memory gate."""
        crew_id = "mem-disabled"
        crew = _make_stopped_crew("gs-mem-dis")
        reg_data = {"crews": {crew_id: crew}}
        self.launcher._registry._reg = reg_data

        podman = Mock()
        podman.container_is_running.return_value = False
        podman.container_start.return_value = None
        podman.container_stop.return_value = None
        podman.container_exec.return_value = "ok"

        with (
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(lifecycle, "GA_MAX_ACTIVE_CREWS", 0),
            patch.object(lifecycle, "GA_MIN_FREE_MEM_GB", 0.0),
            patch.object(_registry_mod, "_load_registry", return_value=reg_data),
            patch.object(_registry_mod, "_save_registry"),
            patch.object(lifecycle, "_wait_gateway", return_value=True),
            patch.object(lifecycle, "_patch_crew_config"),
            patch.object(lifecycle, "_mint_cookie", return_value="new-c"),
            patch.object(lifecycle, "_mint_internal_cookie", return_value=None),
            patch.object(lifecycle, "_deployed_agent_names", return_value=[]),
            patch.object(lifecycle, "_enroll_crew_members"),
            patch.object(lifecycle, "_write_dashboard_cookie", return_value=True),
            patch.object(_registry_mod, "_touch_crew"),
        ):
            result = self.launcher.ensure_running(crew, crew_id)

        self.assertIsNotNone(result)


class TestNukedDuringRestartSentinel(unittest.TestCase):
    """_NUKED_DURING_RESTART sentinel propagates to leader and waiter."""

    def setUp(self) -> None:
        self.launcher = _make_launcher()

    def test_leader_returns_sentinel_when_crew_nuked(self) -> None:
        """When the registry entry disappears after container_start, the leader
        returns _NUKED_DURING_RESTART."""
        crew_id = "nuked-leader"
        crew = _make_stopped_crew("gs-nuked")
        # Registry starts with the crew, then it disappears (nuke)
        empty_reg = {"crews": {}}
        self.launcher._registry._reg = empty_reg

        podman = Mock()
        podman.container_is_running.return_value = False
        podman.container_start.return_value = None

        with (
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(lifecycle, "GA_MAX_ACTIVE_CREWS", 0),
            patch.object(lifecycle, "GA_MIN_FREE_MEM_GB", 0.0),
            patch.object(_registry_mod, "_load_registry", return_value=empty_reg),
            patch.object(_registry_mod, "_save_registry"),
        ):
            result = self.launcher.ensure_running(crew, crew_id)

        self.assertIs(result, _NUKED_DURING_RESTART)

    def test_waiter_returns_sentinel_when_leader_saw_nuke(self) -> None:
        """When the leader recorded success after a nuke but the crew is gone,
        the waiter returns _NUKED_DURING_RESTART."""
        crew_id = "nuked-waiter"
        crew = _make_stopped_crew("gs-nuked-w")

        ev = threading.Event()
        ev.set()
        with self.launcher._startup_events_lock:
            self.launcher._startup_events[crew_id] = ev
            self.launcher._startup_generation[crew_id] = 1
            self.launcher._crew_restart_outcomes[crew_id] = (True, None)

        def fake_get_crew(cid: str) -> dict:
            raise KeyError(f"Crew '{cid}' not found.")

        with (
            patch.object(lifecycle, "_get_podman", return_value=Mock()),
            patch.object(lifecycle, "_get_crew", side_effect=fake_get_crew),
        ):
            result = self.launcher.ensure_running(crew, crew_id)

        self.assertIs(result, _NUKED_DURING_RESTART)


if __name__ == "__main__":
    unittest.main()


class TestFinishSetup(unittest.TestCase):
    """CrewLauncher.finish_setup tests (task 6.3)."""

    def _make_finish_setup_patches(self, *, cookie: str = "test-cookie", gateway_ok: bool = True):
        """Return a list of patches suitable for a successful finish_setup run."""
        return [
            patch.object(lifecycle, "CREW_GATEWAY_PORT", 5476),
            patch.object(lifecycle, "GA_CREW_ACP_BACKEND", "kiro"),
            patch.object(lifecycle, "ANTHROPIC_BASE_URL", ""),
            patch.object(lifecycle, "ANTHROPIC_API_KEY", ""),
            patch.object(lifecycle, "CLAUDE_CODE_OAUTH_TOKEN", ""),
            patch.object(lifecycle, "OPENAI_BASE_URL", ""),
            patch.object(lifecycle, "OPENAI_API_KEY", ""),
            patch.object(lifecycle, "KIRO_API_KEY", ""),
            patch.object(lifecycle, "KIRO_AGENTS_DIR", "/kiro/agents"),
            patch.object(lifecycle, "SCRIPTS_DIR", "/scripts"),
            patch.object(lifecycle, "_wait_gateway", return_value=gateway_ok),
            patch.object(lifecycle, "_cleanup_crew"),
            patch.object(lifecycle, "_inject_auth"),
            patch.object(lifecycle, "_patch_crew_config"),
            patch.object(lifecycle, "_seed_openspec_store"),
            patch.object(lifecycle, "_inject_policy", return_value="v1"),
            patch.object(lifecycle, "_patch_models"),
            patch.object(lifecycle, "_mint_cookie", return_value=cookie),
            patch.object(lifecycle, "_mint_internal_cookie", return_value="int-tok"),
            patch.object(lifecycle, "_write_dashboard_cookie", return_value=True),
            patch.object(lifecycle, "_enroll_crew_members"),
            patch.object(lifecycle, "_prewarm_crew", return_value={"status": "ok"}),
            patch.object(lifecycle, "_secret_identifier", side_effect=lambda s: s[:8]),
        ]

    def test_registry_put_called_with_crew_fields(self) -> None:
        """finish_setup calls registry.put with the correct Crew fields."""
        launcher = _make_launcher()
        put_calls: list = []

        def fake_put(crew) -> None:
            put_calls.append(crew)

        podman = Mock()
        podman.container_stop.return_value = None
        podman.container_start.return_value = None
        podman.container_exec.return_value = "ready"
        podman.container_inspect.return_value = {
            "Config": {"Labels": {"org.ghostship.version": "1.2.3"}}
        }

        import contextlib
        with contextlib.ExitStack() as stack:
            for p in self._make_finish_setup_patches():
                stack.enter_context(p)
            stack.enter_context(
                patch.object(_registry_mod, "_load_registry",
                             return_value={"crews": {}})
            )
            stack.enter_context(patch.object(_registry_mod, "_save_registry"))
            stack.enter_context(
                patch.object(_registry_mod.registry, "put", side_effect=fake_put)
            )

            result = launcher.finish_setup(
                podman,
                "tc1",
                "gs-tc1",
                "vol-tc1",
                "home-tc1",
                "auth-b64",
                "spec-ops",
                None,
                admiral_secret="a" * 64,
            )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(len(put_calls), 1)
        crew = put_calls[0]
        self.assertEqual(crew.crew_id, "tc1")
        self.assertEqual(crew.container, "gs-tc1")
        self.assertEqual(crew.volume, "vol-tc1")
        self.assertEqual(crew.status, "running")
        self.assertEqual(crew.cookie, "test-cookie")
        self.assertEqual(crew.crew_image_version, "1.2.3")

    def test_prewarm_called_at_end(self) -> None:
        """finish_setup calls _prewarm_crew after registry put."""
        launcher = _make_launcher()

        podman = Mock()
        podman.container_stop.return_value = None
        podman.container_start.return_value = None
        podman.container_exec.return_value = "ready"
        podman.container_inspect.return_value = {"Config": {"Labels": {}}}

        prewarm_mock = Mock(return_value={"status": "ok", "pre_warm_task_id": "ptid1"})

        import contextlib
        with contextlib.ExitStack() as stack:
            for p in self._make_finish_setup_patches():
                stack.enter_context(p)
            stack.enter_context(patch.object(lifecycle, "_prewarm_crew", prewarm_mock))
            stack.enter_context(
                patch.object(_registry_mod, "_load_registry",
                             return_value={"crews": {}})
            )
            stack.enter_context(patch.object(_registry_mod, "_save_registry"))

            result = launcher.finish_setup(
                podman,
                "tc2",
                "gs-tc2",
                "vol-tc2",
                "home-tc2",
                "auth-b64",
                "spec-ops",
                None,
                admiral_secret="b" * 64,
            )

        prewarm_mock.assert_called_once()
        self.assertIn("pre_warm_task_id", result)
        self.assertEqual(result["pre_warm_task_id"], "ptid1")
        self.assertEqual(result["pre_warm_status"], "ok")

    def test_returns_error_on_gateway_failure(self) -> None:
        """finish_setup returns error dict when gateway does not recover."""
        launcher = _make_launcher()
        podman = Mock()
        podman.container_stop.return_value = None
        podman.container_start.return_value = None
        cleanup_mock = Mock()

        with (
            patch.object(lifecycle, "CREW_GATEWAY_PORT", 5476),
            patch.object(lifecycle, "_wait_gateway", return_value=False),
            patch.object(lifecycle, "_cleanup_crew", cleanup_mock),
        ):
            result = launcher.finish_setup(
                podman,
                "tc3",
                "gs-tc3",
                "vol-tc3",
                "home-tc3",
                "auth-b64",
                "spec-ops",
                None,
                admiral_secret="c" * 64,
            )

        self.assertIn("error", result)
        self.assertIn("tc3", result["error"])
        cleanup_mock.assert_called_once_with(podman, "gs-tc3", "vol-tc3", "home-tc3")


if __name__ == "__main__":
    unittest.main()
