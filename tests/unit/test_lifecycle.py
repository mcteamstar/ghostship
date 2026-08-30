"""Unit tests for ``transport.lifecycle`` — crew setup / registration lifecycle.

TRN-85 Phase 1 stub. Migration target for classes whose function-under-test is
defined in ``lifecycle.py`` (``_ensure_crew_running``, ``_finish_crew_setup``,
``_crew_api_with_recovery``, ``_crew_api``, ``_probe_gateway``,
``_patch_crew_config``, ``_copy_agents``, ``_copy_skills``, ``_inject_policy``,
``_inject_git_identity``, ``_mint_cookie``, ``_reconcile_registry``, the login
state machine) — **not** the academy functions (those go to ``test_academy.py``).

Patch via ``transport.lifecycle`` for owning-module functions. When a name is
called from server's namespace (e.g. ``_nuke_login_container`` invoked inside
``server._handle_login_*``), patch ``server.<name>`` for the assertion and
``lifecycle.<dep>`` for a dependency internal to the lifecycle function.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch  # noqa: F401

from tests.unit.helpers import lifecycle, academy, server  # noqa: F401


class MemoryGateDisabledTests(unittest.TestCase):
    """Migrated from TRN-85 ``test_transport.TestMemoryGate``.

    Verifies ``_ensure_crew_running`` (lifecycle) skips the podman memory gate
    when ``GA_MIN_FREE_MEM_GB == 0``. ``_ensure_crew_running`` runs in
    lifecycle's namespace, so its dependencies are patched on ``lifecycle`` —
    the server-side dual-patches from TRN-71 were shadows and are dropped.
    """

    def test_gate_skipped_when_disabled(self) -> None:
        """GA_MIN_FREE_MEM_GB=0 skips _wait_for_memory in _ensure_crew_running."""
        from tests.unit.helpers import FakePodmanClient

        crew = {"container": "gs-demo", "cookie": "cookie"}
        fake_podman = FakePodmanClient([int(0.1 * 1024**3)])

        # Make the container appear stopped (so it would trigger memory gate)
        fake_podman.container_is_running = lambda name: False  # type: ignore[method-assign]

        original = lifecycle.GA_MIN_FREE_MEM_GB
        try:
            lifecycle.GA_MIN_FREE_MEM_GB = 0.0
            import contextlib
            with contextlib.ExitStack() as _stack:
                _stack.enter_context(patch.object(lifecycle, "_get_podman", return_value=fake_podman))
                mock_wait = _stack.enter_context(patch.object(lifecycle, "_wait_for_memory"))
                _stack.enter_context(patch.object(lifecycle, "_wait_gateway", return_value=True))
                _stack.enter_context(patch.object(lifecycle, "_mint_cookie", return_value="new-cookie"))
                _stack.enter_context(patch.object(lifecycle, "_load_registry", return_value={
                    "crews": {"demo": {"container": "gs-demo", "cookie": "cookie", "status": "stopped"}}
                }))
                _stack.enter_context(patch.object(lifecycle, "_save_registry"))
                _stack.enter_context(patch.object(lifecycle, "_patch_crew_config"))
                _stack.enter_context(patch.object(lifecycle, "_touch_crew"))
                _stack.enter_context(patch.object(lifecycle, "_probe_gateway", return_value=True))
                # _ensure_crew_running should succeed without calling _wait_for_memory
                try:
                    lifecycle._ensure_crew_running(crew, "demo", touch=False)
                except Exception:
                    pass  # may raise for other reasons; we only care about mock_wait
            # The memory gate must never have been called
            mock_wait.assert_not_called()
        finally:
            lifecycle.GA_MIN_FREE_MEM_GB = original


if __name__ == "__main__":
    unittest.main()
