"""Unit tests for ``transport.lifecycle`` — crew setup / registration lifecycle.

TRN-85 migration target for classes whose function-under-test is defined in
``lifecycle.py`` (``_ensure_crew_running``, ``_finish_crew_setup``,
``_crew_api_with_recovery``, ``_crew_api``, ``_probe_gateway``,
``_patch_crew_config``, ``_copy_agents``, ``_copy_skills``, ``_inject_policy``,
``_inject_git_identity``, ``_mint_cookie``, ``_reconcile_registry``,
``_reseed_crew_schedules``, ``_nuke_login_container``) — **not** the academy
functions (those go to ``test_academy.py``).

Patch-target rule (design.md §2, the call-site principle):

* A function defined in ``lifecycle.py`` reads its dependencies from
  lifecycle's globals, so patch ``lifecycle.X`` **exclusively**. The
  ``server.X`` twins from the TRN-71 dual-patch workaround were shadows and
  are dropped here.
* A route handler / MCP tool defined in ``server.py`` (``_handle_login_*``,
  ``_handle_logout_post``, ``launch``, ``crews``) resolves the lifecycle names
  it calls from **server's** namespace (``from transport.lifecycle import …``),
  so those call sites are patched ``server.X``. ``_get_podman`` is imported
  into both namespaces from ``transport.podman``; patch it on whichever module
  owns the function under test.

Task 2.9 (``SetupRegistrationTests``) named a class that does not exist in
``test_transport.py`` — the design.md §3 inventory is explicitly a starting
guess to be verified against ``grep "^class "``. Lifecycle setup/registration
behaviour is covered by ``LifecycleRegressionTests`` (``_finish_crew_setup``
last-used init) and ``ReconcileRegistryTests``; both are migrated below.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

from tests.unit.helpers import (  # noqa: F401
    FakePodmanClient,
    academy,
    lifecycle,
    server,
)
import transport.registry as _registry_mod
import transport.files as _files_mod


# ── Support fakes (migrated from test_transport.py) ──────────────────────────


class Request:
    """Minimal Starlette-style request stand-in for file PUT handler tests."""

    def __init__(
        self,
        crew_id: str,
        path: str,
        body: bytes,
        query_params: dict[str, str] | None = None,
    ) -> None:
        self.path_params = {"crew_id": crew_id, "path": path}
        self.query_params = query_params or {}
        self._body = body

    async def body(self) -> bytes:
        return self._body


class SetupPodman:
    """PodmanClient stand-in recording stop/start counts for _finish_crew_setup."""

    def __init__(self) -> None:
        self.stops = 0
        self.starts = 0

    def container_stop(self, container: str) -> None:
        self.stops += 1

    def container_start(self, container: str) -> None:
        self.starts += 1

    def container_exec(
        self,
        container: str,
        cmd: list[str],
        env: dict[str, str] | None = None,
    ) -> str:
        return "ready"


class ReconcilePodman:
    """Mock PodmanClient for _reconcile_registry tests."""

    def __init__(
        self,
        containers_exist: dict[str, bool] | None = None,
        containers_running: dict[str, bool] | None = None,
        start_raises: dict[str, Exception] | None = None,
        all_containers: list[dict] | None = None,
    ) -> None:
        self.containers_exist = containers_exist or {}
        self.containers_running = containers_running or {}
        self.start_raises = start_raises or {}
        self.all_containers = all_containers or []
        self.starts: list[str] = []
        self.stops: list[str] = []

    def _req(self, method: str, path: str, **kwargs: Any) -> list:
        return self.all_containers

    def container_exists(self, name: str) -> bool:
        return self.containers_exist.get(name, True)

    def container_is_running(self, name: str) -> bool:
        return self.containers_running.get(name, False)

    def container_start(self, name: str) -> None:
        if name in self.start_raises:
            raise self.start_raises[name]
        self.starts.append(name)

    def container_stop(self, name: str) -> None:
        self.stops.append(name)

    def container_exec(self, name: str, cmd: list[str], env: dict | None = None) -> str:
        return "ready"


def _make_registry_file(tmp_dir: Path, crews: dict[str, dict]) -> Path:
    """Create a temporary registry JSON file for test isolation."""
    registry_path = tmp_dir / "crews.json"
    registry_path.write_text(json.dumps({"crews": crews}))
    return registry_path


class MemoryGateDisabledTests(unittest.TestCase):
    """Migrated from TRN-85 ``test_transport.TestMemoryGate``.

    Verifies ``_ensure_crew_running`` (lifecycle) skips the podman memory gate
    when ``GA_MIN_FREE_MEM_GB == 0``. ``_ensure_crew_running`` runs in
    lifecycle's namespace, so its dependencies are patched on ``lifecycle`` —
    the server-side dual-patches from TRN-71 were shadows and are dropped.
    """

    def test_gate_skipped_when_disabled(self) -> None:
        """GA_MIN_FREE_MEM_GB=0 skips _wait_for_memory in _ensure_crew_running."""
        crew = {"container": "gs-demo", "cookie": "cookie"}
        fake_podman = FakePodmanClient([int(0.1 * 1024**3)])

        # Make the container appear stopped (so it would trigger memory gate)
        fake_podman.container_is_running = lambda name: False  # type: ignore[method-assign]

        original = lifecycle.GA_MIN_FREE_MEM_GB
        try:
            lifecycle.GA_MIN_FREE_MEM_GB = 0.0
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


# ── LifecycleRegressionTests (task 2.9/2.10) ─────────────────────────────────
#
# This class mixes MCP-tool tests (``server.supply``, ``server.nuke`` — bodies
# in server.py, patched ``server.X``) with a lifecycle test
# (``server._finish_crew_setup`` — body in lifecycle.py, patched
# ``lifecycle.X``). The dual-patches from TRN-71 are collapsed per call site.


class LifecycleRegressionTests(unittest.TestCase):
    """Regression tests for supply-recovery, nuke, and finish-crew-setup."""

    def test_supply_recovers_before_signing_upload_url(self) -> None:
        # ``server.supply`` body resolves _require_crew / _ensure_crew_running /
        # _sign_upload_url from server's namespace → patch server.X.
        events: list[str] = []
        crew = {"container": "gs-demo", "cookie": "old"}

        def ensure(value: dict, crew_id: str) -> dict:
            events.append("ensure")
            return value

        def sign(crew_id: str, path: str, **kwargs: object) -> str:
            events.append("sign")
            return "http://localhost/files/demo/repo/file"

        with (
            patch.object(server, "_require_crew", return_value=crew),
            patch.object(server, "_ensure_crew_running", side_effect=ensure),
            patch.object(server, "_sign_upload_url", side_effect=sign),
        ):
            result = server.supply("repo/file", crew_id="demo")

        self.assertEqual(result["delivery_url"], "http://localhost/files/demo/repo/file")
        self.assertEqual(events, ["ensure", "sign"])

    def test_supply_returns_restart_runtime_error_without_signing(self) -> None:
        with (
            patch.object(server, "_require_crew", return_value={"container": "gs-demo"}),
            patch.object(
                server,
                "_ensure_crew_running",
                side_effect=RuntimeError("gateway restart failed"),
            ),
            patch.object(server, "_sign_upload_url") as sign,
        ):
            result = server.supply("repo/file", crew_id="demo")

        self.assertEqual(result, {"error": "gateway restart failed"})
        sign.assert_not_called()

    def test_file_post_retains_restart_recovery_check(self) -> None:
        # ``_handle_file_put`` is defined in files.py; it resolves
        # _ensure_crew_running / _require_crew through files'
        # ``_resolve_orchestration`` helper, which does
        # ``from transport.lifecycle import _ensure_crew_running, _require_crew``
        # at call time → the effective binding is lifecycle.X, so patch there.
        # The files helpers (_verify_file_token / _get_podman / _transfer_upload)
        # are called from the files module's namespace → patch _files_mod.X.
        request = Request("demo", "repo/file", b"payload")
        crew = {"container": "gs-demo"}
        with (
            patch.object(_files_mod, "_verify_file_token", return_value=True),
            patch.object(lifecycle, "_require_crew", return_value=crew),
            patch.object(lifecycle, "_ensure_crew_running", return_value=crew) as ensure,
            patch.object(_files_mod, "_get_podman", return_value=Mock()),
            patch.object(_files_mod, "_transfer_upload", return_value="wrote payload"),
        ):
            response = asyncio.run(server._handle_file_put(request))

        ensure.assert_called_once_with(crew, "demo")
        body = response.body.decode() if isinstance(response.body, bytes) else response.body
        self.assertEqual(body, "wrote payload")

    def test_setup_registration_initializes_last_used(self) -> None:
        # ``_finish_crew_setup`` is defined in lifecycle.py → its dependencies
        # resolve from lifecycle's namespace. Registry path constants are read
        # by _save_registry (registry.py) → patch _registry_mod. server.supply
        # is not involved here.
        podman = SetupPodman()
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            registry = data_dir / "crews.json"
            before = time.time()
            with (
                patch.object(_registry_mod, "DATA_DIR", data_dir),
                patch.object(_registry_mod, "REGISTRY_PATH", registry),
            ):
                _patches = [
                    patch.object(lifecycle, "_wait_gateway", return_value=True),
                    patch.object(lifecycle, "_inject_auth"),
                    patch.object(lifecycle, "_patch_crew_config"),
                    patch.object(lifecycle, "_copy_agents"),
                    patch.object(lifecycle, "_copy_skills"),
                    patch.object(lifecycle, "_copy_steering"),
                    patch.object(lifecycle, "_seed_openspec_store"),
                    patch.object(lifecycle, "_patch_models"),
                    patch.object(lifecycle, "_mint_cookie", return_value="cookie"),
                ]
                with contextlib.ExitStack() as stack:
                    for p in _patches:
                        stack.enter_context(p)
                    result = server._finish_crew_setup(
                        podman,
                        "demo",
                        "gs-demo",
                        "gs-vol-demo",
                        "gs-home-demo",
                        "auth-b64",
                    )

            self.assertEqual(result["status"], "ready")
            record = registry.read_text()
            self.assertIn('"last_used"', record)
            last_used = json.loads(record)["crews"]["demo"]["last_used"]
            self.assertGreaterEqual(last_used, before)

    def test_nuke_clears_captain_order_lock(self) -> None:
        # ``server.nuke`` body resolves its deps from server's namespace.
        crew = {
            "container": "gs-demo",
            "volume": "gs-vol-demo",
            "home_volume": "gs-home-demo",
        }
        registry = {"crews": {"demo": crew}}
        server._captain_order_locks["demo"] = threading.Lock()
        try:
            with (
                patch.object(server, "_get_crew", return_value=crew),
                patch.object(server, "_get_podman", return_value=Mock()),
                patch.object(server, "_cleanup_crew"),
                patch.object(server, "_load_registry", return_value=registry),
                patch.object(server, "_save_registry"),
            ):
                result = server.nuke("demo", confirm=True)
        finally:
            server._captain_order_locks.pop("demo", None)

        self.assertEqual(result["status"], "nuked")
        self.assertNotIn("demo", server._captain_order_locks)

    def test_nuke_partial_registry_entry_failed_launch(self) -> None:
        """nuke() must succeed when registry entry has only container+status (failed launch)."""
        partial_crew = {
            "container": "gs-half",
            "status": "launching",
        }
        registry = {"crews": {"half": partial_crew}}
        mock_podman = Mock()
        with (
            patch.object(server, "_get_crew", return_value=partial_crew),
            patch.object(server, "_get_podman", return_value=mock_podman),
            patch.object(server, "_load_registry", return_value=registry),
            patch.object(server, "_save_registry"),
        ):
            result = server.nuke("half", confirm=True)

        self.assertEqual(result["status"], "nuked")
        self.assertEqual(result["container"], "gs-half")
        self.assertNotIn("error", result)

    def test_nuke_partial_registry_dry_run(self) -> None:
        """nuke() dry-run must not KeyError on a partial registry entry."""
        partial_crew = {
            "container": "gs-half",
            "status": "launching",
        }
        with patch.object(server, "_get_crew", return_value=partial_crew):
            result = server.nuke("half", confirm=False)

        self.assertIn("warning", result)
        self.assertEqual(result["container"], "gs-half")
        self.assertIn("gs-vol-half", result["volumes"])
        self.assertIn("gs-home-half", result["volumes"])


# ── ReconcileRegistryTests (task 2.11) ───────────────────────────────────────
#
# ``_reconcile_registry`` and ``_reseed_crew_schedules`` are defined in
# lifecycle.py, so every dependency (_get_podman / _load_registry /
# _save_registry / _wait_gateway / _mint_cookie / _nuke_login_container /
# _patch_crew_config / _crew_api) resolves from lifecycle's globals. The tests
# call them via the server re-export (same function object) but patch on
# ``lifecycle`` exclusively. server.REGISTRY_PATH was a shadow and is dropped.


class ReconcileRegistryTests(unittest.TestCase):
    """Tests for _reconcile_registry (trn-17 tasks 2.x and 3.x)."""

    def test_orphaned_login_container_swept_on_startup(self) -> None:
        """2.1: orphaned ga-login-* container is swept on startup."""
        podman = ReconcilePodman(
            all_containers=[{"Names": ["/ga-login-stale1234"]}],
        )
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = _make_registry_file(Path(tmp), {})
            with (
                patch.object(lifecycle, "_get_podman", return_value=podman),
                patch.object(_registry_mod, "REGISTRY_PATH", registry_path),
                patch.object(lifecycle, "_nuke_login_container") as nuke,
                patch.object(lifecycle, "_load_registry", return_value={"crews": {}}),
                patch.object(lifecycle, "_save_registry"),
            ):
                server._reconcile_registry()

            nuke.assert_called_once_with(podman, "ga-login-stale1234")

    def test_gone_crew_removed_from_registry(self) -> None:
        """2.2: crew whose container doesn't exist is removed from registry."""
        podman = ReconcilePodman(
            containers_exist={"gs-gone": False},
            all_containers=[],
        )
        crews = {"gone-crew": {"container": "gs-gone", "status": "running"}}
        saved = {}

        def save_reg(reg: dict) -> None:
            saved.update(reg)

        with (
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(lifecycle, "_load_registry", return_value={"crews": dict(crews)}),
            patch.object(lifecycle, "_save_registry", side_effect=save_reg),
        ):
            server._reconcile_registry()

        self.assertNotIn("gone-crew", saved.get("crews", {}))

    def test_stopped_crew_restarted_cookie_refreshed(self) -> None:
        """2.3: stopped crew is restarted, cookie refreshed, status set to running."""
        podman = ReconcilePodman(
            containers_exist={"gs-test": True},
            containers_running={"gs-test": False},
            all_containers=[],
        )
        crews = {"test-crew": {"container": "gs-test", "status": "stopped", "cookie": "old"}}
        saved = {}

        def save_reg(reg: dict) -> None:
            saved.update(reg)

        with (
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(lifecycle, "_load_registry", return_value={"crews": dict(crews)}),
            patch.object(lifecycle, "_save_registry", side_effect=save_reg),
            patch.object(lifecycle, "_wait_gateway", return_value=True),
            patch.object(lifecycle, "_mint_cookie", return_value="new-cookie"),
        ):
            server._reconcile_registry()

        self.assertIn("gs-test", podman.starts)
        crew_entry = saved["crews"]["test-crew"]
        self.assertEqual(crew_entry["status"], "running")
        self.assertEqual(crew_entry["cookie"], "new-cookie")

    def test_stopped_crew_gateway_fails_marked_stopped(self) -> None:
        """2.4: stopped crew whose gateway fails to start is marked stopped (not removed)."""
        podman = ReconcilePodman(
            containers_exist={"gs-fail": True},
            containers_running={"gs-fail": False},
            all_containers=[],
        )
        crews = {"fail-crew": {"container": "gs-fail", "status": "stopped"}}
        saved = {}

        def save_reg(reg: dict) -> None:
            saved.update(reg)

        with (
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(lifecycle, "_load_registry", return_value={"crews": dict(crews)}),
            patch.object(lifecycle, "_save_registry", side_effect=save_reg),
            patch.object(lifecycle, "_wait_gateway", return_value=False),
        ):
            server._reconcile_registry()

        self.assertIn("fail-crew", saved["crews"])
        self.assertEqual(saved["crews"]["fail-crew"]["status"], "stopped")

    def test_running_crew_left_unchanged(self) -> None:
        """2.5: running crew is left unchanged."""
        podman = ReconcilePodman(
            containers_exist={"gs-live": True},
            containers_running={"gs-live": True},
            all_containers=[],
        )
        crews = {"live-crew": {"container": "gs-live", "status": "running", "cookie": "c"}}
        saved = {}

        def save_reg(reg: dict) -> None:
            saved.update(reg)

        with (
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(lifecycle, "_load_registry", return_value={"crews": dict(crews)}),
            patch.object(lifecycle, "_save_registry", side_effect=save_reg),
        ):
            server._reconcile_registry()

        self.assertIn("live-crew", saved["crews"])
        self.assertEqual(saved["crews"]["live-crew"]["cookie"], "c")
        self.assertEqual(podman.starts, [])

    def test_stale_launching_entry_with_missing_container_removed(self) -> None:
        """2.6: stale 'launching' entry with missing container is removed."""
        podman = ReconcilePodman(
            containers_exist={"gs-stale": False},
            all_containers=[],
        )
        crews = {"stale-crew": {"container": "gs-stale", "status": "launching"}}
        saved = {}

        def save_reg(reg: dict) -> None:
            saved.update(reg)

        with (
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(lifecycle, "_load_registry", return_value={"crews": dict(crews)}),
            patch.object(lifecycle, "_save_registry", side_effect=save_reg),
        ):
            server._reconcile_registry()

        self.assertNotIn("stale-crew", saved.get("crews", {}))

    def test_crew_removed_between_snapshot_and_writeback_not_resurrected(self) -> None:
        """3.2: crew removed by another thread between snapshot and write-back is NOT resurrected."""
        podman = ReconcilePodman(
            containers_exist={"gs-del": True},
            containers_running={"gs-del": False},
            all_containers=[],
        )
        load_count = [0]

        def load_registry() -> dict:
            load_count[0] += 1
            if load_count[0] == 1:
                return {"crews": {"del-crew": {"container": "gs-del", "status": "stopped"}}}
            return {"crews": {}}  # Another thread removed it

        saved = {}

        def save_reg(reg: dict) -> None:
            saved.update(reg)

        with (
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(lifecycle, "_load_registry", side_effect=load_registry),
            patch.object(lifecycle, "_save_registry", side_effect=save_reg),
            patch.object(lifecycle, "_wait_gateway", return_value=True),
            patch.object(lifecycle, "_mint_cookie", return_value="new"),
        ):
            server._reconcile_registry()

        self.assertNotIn("del-crew", saved.get("crews", {}))

    def test_reseed_registers_missing_jobs(self) -> None:
        """4.3 — _reseed_crew_schedules POSTs missing jobs to gateway (D8 in TRN-39)."""
        crew_info = {
            "container": "gs-demo", "cookie": "cookie",
            "schedules": [{
                "job_id": "missing-j1", "name": "daily-report",
                "interval_secs": 86400, "cron_expr": None,
                "agent": "ghost", "message": "report", "model": "claude-sonnet-5",
                "enabled": True, "next_fire_at": time.time() + 1000,
            }],
        }
        reg = {"crews": {"demo": crew_info}}
        api_calls = []

        def api(_crew, method, path, **kwargs):
            api_calls.append((method, path, kwargs))
            if method == "GET" and path == "/api/crons":
                return {"jobs": []}  # job absent from gateway
            if method == "POST" and path == "/api/crons":
                return {"id": "new-missing-j1"}
            return {}

        crew = {"container": "gs-demo", "cookie": "cookie"}
        save_calls: list[dict] = []

        def fake_save(r):
            save_calls.append(json.loads(json.dumps(r)))

        with (
            patch.object(lifecycle, "_load_registry", return_value=reg),
            patch.object(lifecycle, "_crew_api", side_effect=api),
            patch.object(lifecycle, "_save_registry", side_effect=fake_save),
        ):
            server._reseed_crew_schedules(crew, "demo", crew_info)

        post_calls = [(m, p, kw) for m, p, kw in api_calls if m == "POST" and p == "/api/crons"]
        self.assertEqual(len(post_calls), 1, f"Expected one POST /api/crons; got: {post_calls}")
        posted_body = post_calls[0][2].get("json", {})
        self.assertEqual(posted_body.get("name"), "daily-report")
        self.assertEqual(posted_body.get("every"), 86400)
        self.assertEqual(posted_body.get("model"), "claude-sonnet-5")

    def test_reconcile_patch_before_gateway_wait_ordering(self) -> None:
        """_reconcile_registry applies _patch_crew_config before _wait_gateway.

        KiroCrew 0.4.0 requires config.local.json (including the required
        'agent' field) to be present before the gateway starts reading it.
        Writing the patch after _wait_gateway means the gateway has already
        loaded config.local.json and will ignore the patch until the next
        restart. This test records the call order: patch → stop → start → wait.
        """
        podman = ReconcilePodman(
            containers_exist={"gs-order": True},
            containers_running={"gs-order": False},
            all_containers=[],
        )
        crews = {"order-crew": {"container": "gs-order", "status": "stopped"}}
        call_order: list[str] = []

        def patched_patch(p, container):
            call_order.append("patch")

        def wait_gateway(url, timeout=30):
            call_order.append("wait")
            return True

        def mint_cookie(p, container, url):
            call_order.append("mint")
            return "fresh-cookie"

        with (
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(lifecycle, "_load_registry", return_value={"crews": dict(crews)}),
            patch.object(lifecycle, "_save_registry"),
            patch.object(lifecycle, "_patch_crew_config", side_effect=patched_patch),
            patch.object(lifecycle, "_wait_gateway", side_effect=wait_gateway),
            patch.object(lifecycle, "_mint_cookie", side_effect=mint_cookie),
        ):
            server._reconcile_registry()

        self.assertIn("patch", call_order, "patch was never called")
        self.assertIn("wait", call_order, "_wait_gateway was never called")
        patch_idx = call_order.index("patch")
        wait_idx = call_order.index("wait")
        self.assertLess(
            patch_idx, wait_idx,
            f"_patch_crew_config (idx {patch_idx}) must be called BEFORE "
            f"_wait_gateway (idx {wait_idx}). Order was: {call_order}",
        )
        self.assertIn("gs-order", podman.stops,
                      "container must be stopped after patch so config is reloaded")
        self.assertEqual(
            podman.starts.count("gs-order"), 2,
            f"expected 2 starts (provisional + post-patch); got {podman.starts}",
        )


# ── ActiveCrewLimitTests (task 2.12) ─────────────────────────────────────────
#
# ``_ensure_crew_running`` is defined in lifecycle.py → patch lifecycle.X. Two
# methods test MCP tools defined in server.py (``launch``, ``crews``) → those
# call sites resolve their deps from server's namespace, patched server.X. The
# GA_MAX_ACTIVE_CREWS / GA_MAX_CREWS constants are duplicated in both
# namespaces, so the tests assign both module attributes directly (not a patch).
# _wait_gateway / _patch_crew_config are lifecycle functions (task 2.12 note).


class ActiveCrewLimitTests(unittest.TestCase):
    """Tests for GA_MAX_ACTIVE_CREWS enforcement in _ensure_crew_running
    and the active_crews / max_active_crews fields in crews()."""

    def _make_crew(self, status: str = "stopped", container: str = "gs-crew") -> dict:
        return {"status": status, "container": container, "cookie": "c"}

    def _registry_with_running(self, n: int, target_id: str = "target") -> dict:
        """Registry with n running crews plus a stopped target crew."""
        crews: dict = {}
        for i in range(n):
            crews[f"crew-{i}"] = self._make_crew(status="running", container=f"gs-{i}")
        crews[target_id] = self._make_crew(status="stopped", container="gs-target")
        return {"crews": crews}

    def test_startup_event_pruned_when_leader_restart_raises(self) -> None:
        """A failed leader restart always removes its startup event."""
        class FailingRestartPodman:
            def container_is_running(self, name: str) -> bool:
                return False

            def container_start(self, name: str) -> None:
                pass

            def container_stop(self, name: str) -> None:
                pass

        startup_events: dict[str, threading.Event] = {}
        crew = self._make_crew(status="stopped", container="gs-failing")

        with (
            patch.object(lifecycle, "_get_podman", return_value=FailingRestartPodman()),
            patch.object(lifecycle, "_startup_events", startup_events),
            patch.object(lifecycle, "_startup_events_lock", threading.Lock()),
            patch.object(lifecycle, "GA_MAX_ACTIVE_CREWS", 0),
            patch.object(lifecycle, "GA_MIN_FREE_MEM_GB", 0.0),
            patch.object(lifecycle, "_wait_gateway", side_effect=RuntimeError("restart failed")),
        ):
            with self.assertRaisesRegex(RuntimeError, "restart failed"):
                server._ensure_crew_running(crew, "target")

        self.assertNotIn("target", startup_events)

    def test_active_limit_reached_raises(self) -> None:
        """_ensure_crew_running raises RuntimeError when GA_MAX_ACTIVE_CREWS
        running crews already exist and a stopped crew tries to restart."""
        original = lifecycle.GA_MAX_ACTIVE_CREWS
        try:
            lifecycle.GA_MAX_ACTIVE_CREWS = 2
            reg = self._registry_with_running(2)  # 2 running, limit is 2

            class StoppedPodman:
                def container_is_running(self, name: str) -> bool:
                    return False

            with (
                patch.object(lifecycle, "_load_registry", return_value=reg),
                patch.object(lifecycle, "_get_podman", return_value=StoppedPodman()),
                patch.object(lifecycle, "_startup_events", {}),
                patch.object(lifecycle, "_startup_events_lock", threading.Lock()),
            ):
                crew = reg["crews"]["target"]
                with self.assertRaises(RuntimeError) as ctx:
                    server._ensure_crew_running(crew, "target")
            self.assertIn("Active crew limit", str(ctx.exception))
            self.assertIn("2", str(ctx.exception))
        finally:
            lifecycle.GA_MAX_ACTIVE_CREWS = original

    def test_active_limit_not_reached_proceeds(self) -> None:
        """_ensure_crew_running proceeds below the limit with one gateway wait."""
        original = lifecycle.GA_MAX_ACTIVE_CREWS
        try:
            lifecycle.GA_MAX_ACTIVE_CREWS = 3
            reg = self._registry_with_running(1)
            steps: list[str] = []

            class StoppedRestartPodman:
                def __init__(self) -> None:
                    self.starts = 0

                def container_is_running(self, name: str) -> bool:
                    return False

                def container_start(self, name: str) -> None:
                    self.starts += 1
                    steps.append("start")

                def container_stop(self, name: str) -> None:
                    steps.append("stop")

                def container_exec(self, name: str, cmd: list, env: dict | None = None) -> str:
                    return "ok"

            podman = StoppedRestartPodman()
            with contextlib.ExitStack() as _stack:
                _stack.enter_context(patch.object(lifecycle, "_load_registry", return_value=reg))
                _stack.enter_context(patch.object(lifecycle, "_save_registry"))
                _stack.enter_context(patch.object(lifecycle, "_get_podman", return_value=podman))
                _stack.enter_context(patch.object(lifecycle, "_startup_events", {}))
                _stack.enter_context(patch.object(lifecycle, "_startup_events_lock", threading.Lock()))
                _stack.enter_context(patch.object(lifecycle, "GA_MIN_FREE_MEM_GB", 0.0))
                wait_gateway = _stack.enter_context(patch.object(
                    lifecycle,
                    "_wait_gateway",
                    side_effect=lambda *args, **kwargs: (steps.append("wait") or True),
                ))
                _stack.enter_context(patch.object(
                    lifecycle,
                    "_patch_crew_config",
                    side_effect=lambda *args, **kwargs: steps.append("patch"),
                ))
                _stack.enter_context(patch.object(lifecycle, "_mint_cookie", return_value="new-c"))
                crew = reg["crews"]["target"]
                result = server._ensure_crew_running(crew, "target")
            self.assertIsNotNone(result)
            self.assertEqual(podman.starts, 2)
            self.assertEqual(steps, ["start", "patch", "stop", "start", "wait"])
            wait_gateway.assert_called_once_with("http://gs-target:5476", timeout=30)
        finally:
            lifecycle.GA_MAX_ACTIVE_CREWS = original

    def test_active_limit_zero_disables_check(self) -> None:
        """GA_MAX_ACTIVE_CREWS=0 bypasses the active limit — no RuntimeError
        even when many crews are running."""
        original = lifecycle.GA_MAX_ACTIVE_CREWS
        try:
            lifecycle.GA_MAX_ACTIVE_CREWS = 0
            reg: dict = {"crews": {}}
            for i in range(10):
                reg["crews"][f"crew-{i}"] = self._make_crew(
                    status="running", container=f"gs-{i}"
                )
            reg["crews"]["target"] = self._make_crew(status="stopped", container="gs-target")

            class StoppedRestartPodman:
                def container_is_running(self, name: str) -> bool:
                    return False

                def container_start(self, name: str) -> None:
                    pass

                def container_stop(self, name: str) -> None:
                    pass

                def container_exec(self, name: str, cmd: list, env: dict | None = None) -> str:
                    return "ok"

            with (
                patch.object(lifecycle, "_load_registry", return_value=reg),
                patch.object(lifecycle, "_save_registry"),
                patch.object(lifecycle, "_get_podman", return_value=StoppedRestartPodman()),
                patch.object(lifecycle, "_startup_events", {}),
                patch.object(lifecycle, "_startup_events_lock", threading.Lock()),
                patch.object(lifecycle, "GA_MIN_FREE_MEM_GB", 0.0),
                patch.object(lifecycle, "_wait_gateway", return_value=True),
                patch.object(lifecycle, "_patch_crew_config"),
                patch.object(lifecycle, "_mint_cookie", return_value="new-c"),
            ):
                crew = reg["crews"]["target"]
                result = server._ensure_crew_running(crew, "target")
            self.assertIsNotNone(result)
        finally:
            lifecycle.GA_MAX_ACTIVE_CREWS = original

    def test_already_running_crew_not_double_counted(self) -> None:
        """A crew that is already running is not counted against the active limit
        — it returns before the limit check is reached."""
        original = lifecycle.GA_MAX_ACTIVE_CREWS
        try:
            lifecycle.GA_MAX_ACTIVE_CREWS = 1

            class RunningPodman:
                def container_is_running(self, name: str) -> bool:
                    return True

            with (
                patch.object(lifecycle, "_get_podman", return_value=RunningPodman()),
                patch.object(lifecycle, "_probe_gateway", return_value=True) as probe,
                patch.object(lifecycle, "_touch_crew"),
            ):
                crew = self._make_crew(status="running", container="gs-live")
                result = server._ensure_crew_running(crew, "live-crew")

            probe.assert_called_once()
            self.assertEqual(result["container"], "gs-live")
        finally:
            lifecycle.GA_MAX_ACTIVE_CREWS = original

    def test_launch_registered_crew_limit_error_message(self) -> None:
        """launch() returns 'Registered crew limit' error when GA_MAX_CREWS reached."""
        # ``server.launch`` body resolves _load_registry / _get_podman /
        # _read_auth_file / _resolve_composition / _resolve_image from server's
        # namespace → patch server.X.
        original = server.GA_MAX_CREWS
        try:
            server.GA_MAX_CREWS = 20
            crews = {f"crew-{i}": {"status": "stopped", "container": f"gs-{i}"}
                     for i in range(20)}
            reg = {"crews": crews}

            class MinimalPodman:
                pass

            with (
                patch.object(server, "_load_registry", return_value=reg),
                patch.object(server, "_get_podman", return_value=MinimalPodman()),
                patch.object(server, "_read_auth_file", return_value="dummyauth"),
                patch.object(server, "_resolve_composition", return_value={"name": "spec-ops", "dir": "spec-ops"}),
                patch.object(server, "_resolve_image", return_value="localhost/spec-ops:latest"),
            ):
                result = server.launch("new-crew")

            self.assertIn("error", result)
            self.assertIn("Registered crew limit", result["error"])
            self.assertIn("20", result["error"])
            self.assertNotIn("Max crews", result["error"])
        finally:
            server.GA_MAX_CREWS = original

    def test_crews_includes_active_and_max_active_fields(self) -> None:
        """crews() response includes active_crews (int) and max_active_crews (int)."""
        # ``server.crews`` body resolves its deps from server's namespace.
        original = server.GA_MAX_ACTIVE_CREWS
        try:
            server.GA_MAX_ACTIVE_CREWS = 3
            reg = {
                "crews": {
                    "running-a": {"status": "running", "container": "gs-a", "cookie": "c1"},
                    "running-b": {"status": "running", "container": "gs-b", "cookie": "c2"},
                    "stopped-c": {"status": "stopped", "container": "gs-c", "cookie": "c3"},
                }
            }
            fake = FakePodmanClient([int(4 * 1024**3)])
            server._host_memory_cache = None

            with (
                patch.object(server, "_load_registry", return_value=reg),
                patch.object(server, "_get_podman", return_value=fake),
                patch.object(server, "_probe_gateway", return_value=False),
                patch.object(server, "_crew_api", side_effect=Exception("offline")),
            ):
                result = server.crews()

            self.assertIn("active_crews", result)
            self.assertIn("max_active_crews", result)
            self.assertIsInstance(result["active_crews"], int)
            self.assertIsInstance(result["max_active_crews"], int)
            self.assertEqual(result["active_crews"], 2)   # running-a and running-b
            self.assertEqual(result["max_active_crews"], 3)
        finally:
            server.GA_MAX_ACTIVE_CREWS = original


# ── CopyAgentsMcpTests (task 2.13) ───────────────────────────────────────────
#
# ``_copy_agents`` is defined in lifecycle.py and resolves _load_crew_manifest
# (imported into lifecycle from academy), Path, MCP_CATALOGUE_DIR and logger
# from lifecycle's namespace. Task 2.13: patch transport.lifecycle.Path (not
# transport.server.Path); the warning handler goes on lifecycle.logger. The
# server / academy dual-patches from TRN-71 were shadows and are dropped.


class CopyAgentsMcpTests(unittest.TestCase):
    """Tests for the mcp.json writing logic in _copy_agents() (trn-68)."""

    def _extract_mcp_json_from_calls(self, mock_podman: Mock) -> "dict | None":
        """Parse mcp.json content from container_archive_put call args, or None."""
        import io as _io
        import tarfile as _tarfile

        for call in mock_podman.container_archive_put.call_args_list:
            dest_dir: str = call.args[1]
            tar_bytes: bytes = call.args[2]
            if ".kiro" not in dest_dir:
                continue
            buf = _io.BytesIO(tar_bytes)
            with _tarfile.open(fileobj=buf, mode="r") as tf:
                for member in tf.getmembers():
                    if member.name == "mcp.json":
                        raw = tf.extractfile(member)
                        return json.loads(raw.read())
        return None

    def _run(
        self,
        manifest: dict,
        catalogue: dict[str, dict],
        env: "dict[str, str] | None" = None,
    ) -> "tuple[Mock, dict | None, list[str]]":
        """Run _copy_agents and return (podman, mcp_json_or_None, warning_messages)."""
        import os
        import tempfile as _tempfile

        mock_podman = Mock()
        mock_podman.container_archive_put = Mock()
        mock_podman.container_exec = Mock(return_value="")

        captured_warnings: list[str] = []

        with _tempfile.TemporaryDirectory() as tmp:
            mcp_dir = Path(tmp) / "mcp"
            mcp_dir.mkdir()
            for name, content in catalogue.items():
                (mcp_dir / f"{name}.json").write_text(json.dumps(content))

            agents_dir = Path(tmp) / "agents"
            agents_dir.mkdir()

            import logging as _logging

            class _WarningCapture(_logging.Handler):
                def emit(self, record: "_logging.LogRecord") -> None:
                    if record.levelno >= _logging.WARNING:
                        captured_warnings.append(record.getMessage())

            handler = _WarningCapture()
            # _copy_agents runs in lifecycle's namespace, so its own warnings
            # (e.g. unknown server name) emit on lifecycle's logger (task 2.13).
            # It also calls academy._substitute_env_vars, which emits the
            # missing-env-var warning on academy's logger — a genuine
            # cross-module dependency, so both loggers get the handler.
            lifecycle.logger.addHandler(handler)
            academy.logger.addHandler(handler)

            real_path = Path

            def _path_factory(p):
                if str(p) == "/agents":
                    return agents_dir
                return real_path(p)

            try:
                with (
                    patch.object(lifecycle, "_load_crew_manifest", return_value=manifest),
                    patch.object(lifecycle, "MCP_CATALOGUE_DIR", mcp_dir),
                    patch.dict(os.environ, env or {}, clear=False),
                    patch("transport.lifecycle.Path", side_effect=_path_factory),
                ):
                    server._copy_agents(mock_podman, "gs-test", None)
            finally:
                lifecycle.logger.removeHandler(handler)
                academy.logger.removeHandler(handler)

        mcp_json = self._extract_mcp_json_from_calls(mock_podman)
        return mock_podman, mcp_json, captured_warnings

    def test_manifest_with_mcp_servers_writes_mcp_json(self) -> None:
        """3.1 — manifest with mcpServers → correct mcp.json written with resolved entries."""
        manifest = {
            "agents": "*", "skills": "*", "steering": "*",
            "mcpServers": ["armory"],
        }
        catalogue = {
            "armory": {"type": "streamable-http", "url": "http://armory.example.com/mcp"},
        }
        _, mcp_json, _ = self._run(manifest, catalogue)

        self.assertIsNotNone(mcp_json, "mcp.json was not written")
        assert mcp_json is not None
        self.assertIn("mcpServers", mcp_json)
        self.assertIn("armory", mcp_json["mcpServers"])
        self.assertEqual(mcp_json["mcpServers"]["armory"]["type"], "streamable-http")
        self.assertEqual(
            mcp_json["mcpServers"]["armory"]["url"], "http://armory.example.com/mcp"
        )

    def test_manifest_without_mcp_servers_no_mcp_json(self) -> None:
        """3.2 — manifest with no mcpServers key → no mcp.json written."""
        manifest = {"agents": "*", "skills": "*", "steering": "*"}
        catalogue = {
            "armory": {"type": "streamable-http", "url": "http://armory.example.com/mcp"},
        }
        _, mcp_json, _ = self._run(manifest, catalogue)

        self.assertIsNone(mcp_json, "mcp.json should NOT be written when mcpServers absent")

    def test_manifest_with_empty_mcp_servers_no_mcp_json(self) -> None:
        """3.2b — manifest with empty mcpServers list → no mcp.json written."""
        manifest = {"agents": "*", "skills": "*", "steering": "*", "mcpServers": []}
        catalogue = {}
        _, mcp_json, _ = self._run(manifest, catalogue)

        self.assertIsNone(mcp_json, "mcp.json should NOT be written for empty mcpServers")

    def test_unknown_server_name_warns_and_skips(self) -> None:
        """3.3 — unknown server name → warning logged, other servers written, no exception."""
        manifest = {
            "agents": "*", "skills": "*", "steering": "*",
            "mcpServers": ["armory", "nonexistent"],
        }
        catalogue = {
            "armory": {"type": "streamable-http", "url": "http://armory.example.com/mcp"},
        }
        _, mcp_json, warnings = self._run(manifest, catalogue)

        self.assertIsNotNone(mcp_json, "mcp.json should be written for the valid server")
        assert mcp_json is not None
        self.assertIn("armory", mcp_json["mcpServers"])
        self.assertNotIn("nonexistent", mcp_json["mcpServers"])

        self.assertTrue(
            any("nonexistent" in w for w in warnings),
            f"Expected warning about 'nonexistent'; warnings: {warnings}",
        )

    def test_headers_entry_gets_poolable_false(self) -> None:
        """3.4 — catalogue entry with headers → poolable: false added automatically."""
        manifest = {
            "agents": "*", "skills": "*", "steering": "*",
            "mcpServers": ["nexus"],
        }
        catalogue = {
            "nexus": {
                "type": "streamable-http",
                "url": "http://nexus.example.com/mcp",
                "headers": {"Authorization": "Bearer token123"},
            },
        }
        _, mcp_json, _ = self._run(manifest, catalogue)

        self.assertIsNotNone(mcp_json)
        assert mcp_json is not None
        nexus_entry = mcp_json["mcpServers"]["nexus"]
        self.assertFalse(
            nexus_entry.get("poolable", True),
            "Entry with headers should have poolable: false",
        )

    def test_no_headers_entry_no_poolable_added(self) -> None:
        """3.4b — catalogue entry WITHOUT headers does NOT get poolable key added."""
        manifest = {
            "agents": "*", "skills": "*", "steering": "*",
            "mcpServers": ["armory"],
        }
        catalogue = {
            "armory": {"type": "streamable-http", "url": "http://armory.example.com/mcp"},
        }
        _, mcp_json, _ = self._run(manifest, catalogue)

        self.assertIsNotNone(mcp_json)
        assert mcp_json is not None
        self.assertNotIn("poolable", mcp_json["mcpServers"]["armory"])

    def test_env_var_substituted_when_set(self) -> None:
        """3.5 — catalogue entry with ${VAR} → substituted when env var is set."""
        manifest = {
            "agents": "*", "skills": "*", "steering": "*",
            "mcpServers": ["nexus"],
        }
        catalogue = {
            "nexus": {
                "type": "streamable-http",
                "url": "http://nexus.example.com/mcp",
                "headers": {"Authorization": "Bearer ${NEXUS_API_KEY}"},
            },
        }
        _, mcp_json, warnings = self._run(
            manifest, catalogue, env={"NEXUS_API_KEY": "secret-token-xyz"}
        )

        self.assertIsNotNone(mcp_json)
        assert mcp_json is not None
        auth_header = mcp_json["mcpServers"]["nexus"]["headers"]["Authorization"]
        self.assertEqual(auth_header, "Bearer secret-token-xyz")
        self.assertFalse(
            any("NEXUS_API_KEY" in w and "not set" in w for w in warnings),
            f"Should not warn about a set variable; warnings: {warnings}",
        )

    def test_missing_env_var_warns_and_writes_literal(self) -> None:
        """3.6 — catalogue entry with ${MISSING} → warning logged, literal string written,
        setup continues."""
        import os
        manifest = {
            "agents": "*", "skills": "*", "steering": "*",
            "mcpServers": ["nexus"],
        }
        catalogue = {
            "nexus": {
                "type": "streamable-http",
                "url": "http://nexus.example.com/mcp",
                "headers": {"Authorization": "Bearer ${TRN68_MISSING_TEST_VAR}"},
            },
        }
        os.environ.pop("TRN68_MISSING_TEST_VAR", None)
        _, mcp_json, warnings = self._run(manifest, catalogue, env={})

        self.assertIsNotNone(mcp_json, "mcp.json should be written even with missing vars")
        assert mcp_json is not None
        auth_header = mcp_json["mcpServers"]["nexus"]["headers"]["Authorization"]
        self.assertIn("${TRN68_MISSING_TEST_VAR}", auth_header)

        self.assertTrue(
            any("TRN68_MISSING_TEST_VAR" in w for w in warnings),
            f"Expected warning about TRN68_MISSING_TEST_VAR; warnings: {warnings}",
        )


# ── LoginLogoutTests (task 2.14) ─────────────────────────────────────────────
#
# ``_handle_login_post`` / ``_handle_login_get`` / ``_handle_logout_post`` are
# defined in server.py and resolve _get_podman / _start_login_container /
# _nuke_login_container / _read_auth_from_crew / _inject_auth / _read_auth_file
# / _write_auth_file / select / time from server's namespace → patch server.X
# exclusively. Task 2.14: _nuke_login_container lives in lifecycle but is called
# from server's body, so the assertion patches server._nuke_login_container.


class LoginLogoutTests(unittest.TestCase):
    """Tests for POST /login, GET /login, and POST /logout routes."""

    def setUp(self) -> None:
        import transport.server as srv
        with srv._login_pending_lock:
            srv._login_pending = None

    def test_post_login_happy_path_sets_pending_and_returns_url(self) -> None:
        podman = Mock()
        container_name = "ga-login-abcd1234"
        exec_id = "exec-abc"

        output_chunks = [
            b"? Enter Start URL \xe2\x80\xba ",
            b"\x1b[2K\xe2\x9c\x94 Enter Start URL\r\n? Enter Region \xe2\x80\xba ",
            b"\x1b[2K\xe2\x9c\x94 Enter Region\r\n\r\nConfirm the following code in the browser\r\nCode: ABCD-1234\r\n\r\nOpen this URL: https://device.auth.example.com/activate?user_code=ABCD-1234\r\n",
        ]
        chunk_iter = iter(output_chunks)

        fake_sock = Mock()
        fake_sock.fileno.return_value = 5

        def fake_recv(n):
            try:
                return next(chunk_iter)
            except StopIteration:
                return b""

        fake_sock.recv.side_effect = fake_recv

        with (
            patch.object(server, "_read_auth_file", return_value=""),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_start_login_container", return_value=container_name),
            patch.object(server, "select") as mock_select,
            patch.object(podman, "container_exec", return_value="kiro-cli"),
            patch.object(podman, "container_exec_pty_stdin", return_value=(exec_id, fake_sock)),
        ):
            mock_select.select.return_value = ([fake_sock], [], [])
            request = Mock()
            response = asyncio.run(server._handle_login_post(request))

        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertEqual(body["status"], "pending")
        self.assertIn("https://device.auth.example.com", body["login_url"])
        self.assertEqual(body["code"], "ABCD-1234")

        with server._login_pending_lock:
            pending = server._login_pending
        self.assertIsNotNone(pending)
        self.assertEqual(pending["container"], container_name)
        self.assertEqual(pending["exec_id"], exec_id)

    def test_post_login_answers_builder_id_login_method_menu(self) -> None:
        """Builder ID fallback accepts kiro-cli's highlighted default option."""
        podman = Mock()
        container_name = "ga-login-builder123"
        exec_id = "exec-builder"

        output_chunks = [
            (
                b"\x1b[?25l? Select login method \xe2\x80\xba\r\n"
                b"\xe2\x9d\xaf Use with Builder ID\r\n"
                b"  Use with Google\r\n"
                b"  Use with GitHub\r\n"
                b"  Use with Your Organization\r\n"
                b"\x1b[4A\r\x1b[2K\x1b[1B\r\x1b[2K\x1b[1B\r\x1b[2K\x1b[1B\r\x1b[2K\x1b[1B"
                b"\x1b[4A\xe2\x9d\xaf Use with Builder ID\r\n"
                b"  Use with Google\r\n"
                b"  Use with GitHub\r\n"
                b"  Use with Your Organization\r\n"
            ),
            (
                b"\r\nOpen this URL: "
                b"https://device.auth.example.com/activate?user_code=BUILDER-1234\r\n"
            ),
        ]
        chunk_iter = iter(output_chunks)

        fake_sock = Mock()
        fake_sock.fileno.return_value = 5

        def fake_recv(n):
            try:
                return next(chunk_iter)
            except StopIteration:
                return b""

        fake_sock.recv.side_effect = fake_recv

        with (
            patch.object(server, "KIRO_IDENTITY_PROVIDER", ""),
            patch.object(server, "_read_auth_file", return_value=""),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_start_login_container", return_value=container_name),
            patch.object(server, "select") as mock_select,
            patch.object(podman, "container_exec", return_value="kiro-cli"),
            patch.object(
                podman,
                "container_exec_pty_stdin",
                return_value=(exec_id, fake_sock),
            ),
        ):
            mock_select.select.return_value = ([fake_sock], [], [])
            request = Mock()
            response = asyncio.run(server._handle_login_post(request))

        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertEqual(body["status"], "pending")
        self.assertEqual(
            body["login_url"],
            "https://device.auth.example.com/activate?user_code=BUILDER-1234",
        )
        self.assertEqual(body["code"], "BUILDER-1234")
        fake_sock.sendall.assert_called_once_with(b"\n")

    def test_post_login_returns_409_when_already_authenticated(self) -> None:
        with patch.object(server, "_read_auth_file", return_value="dGVzdA=="):
            request = Mock()
            response = asyncio.run(server._handle_login_post(request))

        self.assertEqual(response.status_code, 409)
        self.assertIn("Already authenticated", response.body.decode())

    def test_post_login_returns_409_when_login_already_in_progress(self) -> None:
        with (
            patch.object(server, "_read_auth_file", return_value=""),
            patch.object(server, "_login_pending_lock"),
        ):
            with server._login_pending_lock:
                server._login_pending = {
                    "container": "ga-login-existing",
                    "exec_id": "x",
                    "started_at": 999.0,
                }
            request = Mock()
            response = asyncio.run(server._handle_login_post(request))

        with server._login_pending_lock:
            server._login_pending = None

        self.assertEqual(response.status_code, 409)
        self.assertIn("Login already in progress", response.body.decode())

    def test_post_login_nukes_container_and_returns_500_when_no_url(self) -> None:
        podman = Mock()
        container_name = "ga-login-fail1234"

        fake_sock = Mock()
        fake_sock.fileno.return_value = 5
        fake_sock.recv.return_value = b"Error: misconfigured IdP\n"

        with (
            patch.object(server, "_read_auth_file", return_value=""),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_start_login_container", return_value=container_name),
            patch.object(server, "_nuke_login_container") as nuke,
            patch.object(server, "time") as mock_time,
            patch.object(server, "select") as mock_select,
            patch.object(podman, "container_exec", return_value="kiro-cli"),
            patch.object(podman, "container_exec_pty_stdin", return_value=("exec-fail", fake_sock)),
        ):
            mock_time.time.side_effect = [1000.0, 1000.0, 1016.0]
            mock_select.select.return_value = ([fake_sock], [], [])
            request = Mock()
            response = asyncio.run(server._handle_login_post(request))

        self.assertEqual(response.status_code, 500)
        nuke.assert_called_once_with(podman, container_name)
        with server._login_pending_lock:
            self.assertIsNone(server._login_pending)

    def test_get_login_returns_404_when_no_pending_flow(self) -> None:
        request = Mock()
        response = asyncio.run(server._handle_login_get(request))
        self.assertEqual(response.status_code, 404)
        self.assertIn("No login in progress", response.body.decode())

    def test_get_login_returns_pending_when_auth_not_complete(self) -> None:
        with server._login_pending_lock:
            server._login_pending = {
                "container": "ga-login-abcd",
                "exec_id": "x",
                "started_at": 999.0,
            }

        podman = Mock()
        with (
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_read_auth_from_crew", return_value=None),
        ):
            request = Mock()
            response = asyncio.run(server._handle_login_get(request))

        with server._login_pending_lock:
            server._login_pending = None

        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertEqual(body["status"], "pending")

    def test_get_login_completes_writes_auth_injects_crews_nukes_temp(self) -> None:
        auth_b64 = "dGVzdC1hdXRo"
        running_crew = {"status": "running", "container": "gs-crew1"}
        registry = {"crews": {"crew1": running_crew}}

        with server._login_pending_lock:
            server._login_pending = {
                "container": "ga-login-done",
                "exec_id": "x",
                "started_at": 999.0,
            }

        podman = Mock()
        with (
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_read_auth_from_crew", return_value=auth_b64),
            patch.object(server, "_write_auth_file") as write_auth,
            patch.object(server, "_load_registry", return_value=registry),
            patch.object(server, "_inject_auth") as inject,
            patch.object(server, "_nuke_login_container") as nuke,
        ):
            request = Mock()
            response = asyncio.run(server._handle_login_get(request))

        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertEqual(body["status"], "complete")
        write_auth.assert_called_once_with(auth_b64)
        inject.assert_called_once_with(podman, "gs-crew1", auth_b64)
        nuke.assert_called_once_with(podman, "ga-login-done")

        with server._login_pending_lock:
            self.assertIsNone(server._login_pending)

    def test_post_logout_returns_404_when_not_authenticated(self) -> None:
        with patch.object(server, "_read_auth_file", return_value=""):
            request = Mock()
            response = asyncio.run(server._handle_logout_post(request))

        self.assertEqual(response.status_code, 404)
        self.assertIn("Not authenticated", response.body.decode())

    def test_post_logout_deletes_auth_file_and_clears_running_crews(self) -> None:
        running_crew = {"status": "running", "container": "gs-crew1"}
        stopped_crew = {"status": "stopped", "container": "gs-crew2"}
        registry = {"crews": {"crew1": running_crew, "crew2": stopped_crew}}

        podman = Mock()
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            auth_path = data_dir / server.GA_AUTH_FILE
            auth_path.write_text("dGVzdA==")
            auth_path.chmod(0o600)

            with (
                patch.object(server, "DATA_DIR", data_dir),
                patch.object(server, "_read_auth_file", return_value="dGVzdA=="),
                patch.object(server, "_get_podman", return_value=podman),
                patch.object(server, "_load_registry", return_value=registry),
            ):
                request = Mock()
                response = asyncio.run(server._handle_logout_post(request))

        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertEqual(body["status"], "logged_out")

        containers_cleared = [call.args[0] for call in podman.container_exec.call_args_list]
        self.assertEqual(containers_cleared, ["gs-crew1"])
        self.assertTrue(
            any(
                call.args[1][1].endswith("/wipe_auth.py")
                for call in podman.container_exec.call_args_list
            )
        )


# ── LoginFlowEdgeCaseTests (task 2.15) ───────────────────────────────────────
#
# Same call-site principle as LoginLogoutTests: the login handler bodies are in
# server.py → patch server.X exclusively.


class LoginFlowEdgeCaseTests(unittest.TestCase):
    """Tests for login flow edge cases (trn-17 tasks 7.x)."""

    def setUp(self) -> None:
        with server._login_pending_lock:
            server._login_pending = None

    def test_pty_exec_no_url_within_15s_returns_500_and_cleans_up(self) -> None:
        """7.1: PTY exec with no URL within 15s returns 500 and cleans up container."""
        podman = Mock()
        fake_sock = Mock()
        fake_sock.fileno.return_value = 5
        fake_sock.recv.return_value = b"Loading...\n"

        with (
            patch.object(server, "_read_auth_file", return_value=""),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_start_login_container", return_value="ga-login-timeout"),
            patch.object(server, "_nuke_login_container") as nuke,
            patch.object(server, "time") as mock_time,
            patch.object(server, "select") as mock_select,
            patch.object(podman, "container_exec", return_value="kiro-cli"),
            patch.object(podman, "container_exec_pty_stdin", return_value=("exec-x", fake_sock)),
        ):
            mock_time.time.side_effect = [1000.0, 1000.0, 1016.0]
            mock_select.select.return_value = ([fake_sock], [], [])
            request = Mock()
            response = asyncio.run(server._handle_login_post(request))

        self.assertEqual(response.status_code, 500)
        nuke.assert_called_once_with(podman, "ga-login-timeout")

    def test_region_prompt_answered_with_kiro_region(self) -> None:
        """7.2: Region prompt is answered with KIRO_REGION when encountered."""
        podman = Mock()
        fake_sock = Mock()
        fake_sock.fileno.return_value = 5

        read_sequence = [
            b"? Enter Start URL \xe2\x80\xba ",
            b"\x1b[2K\xe2\x9c\x94 Enter Start URL\r\n? Enter Region \xe2\x80\xba ",
            b"\x1b[2K\xe2\x9c\x94 Enter Region\r\nOpen this URL: https://device.sso.example.com/activate?user_code=TEST-1234\r\nCode: TEST-1234\r\n",
        ]
        read_iter = iter(read_sequence)
        fake_sock.recv.side_effect = lambda n: next(read_iter, b"")
        sends: list[bytes] = []
        fake_sock.sendall.side_effect = lambda data: sends.append(data)

        with (
            patch.object(server, "_read_auth_file", return_value=""),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_start_login_container", return_value="ga-login-region"),
            patch.object(server, "select") as mock_select,
            patch.object(server, "KIRO_REGION", "us-west-2"),
            patch.object(podman, "container_exec", return_value="kiro-cli"),
            patch.object(podman, "container_exec_pty_stdin", return_value=("exec-r", fake_sock)),
        ):
            mock_select.select.return_value = ([fake_sock], [], [])
            request = Mock()
            response = asyncio.run(server._handle_login_post(request))

        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertEqual(body["status"], "pending")
        all_sent = b"".join(sends)
        self.assertIn(b"us-west-2", all_sent)

    def test_concurrent_post_login_while_pending_returns_409(self) -> None:
        """7.3: concurrent POST /login while _login_pending is set returns 409."""
        with server._login_pending_lock:
            server._login_pending = {
                "container": "ga-login-existing",
                "exec_id": "x",
                "started_at": 999.0,
            }

        try:
            with patch.object(server, "_read_auth_file", return_value=""):
                request = Mock()
                response = asyncio.run(server._handle_login_post(request))

            self.assertEqual(response.status_code, 409)
            self.assertIn("Login already in progress", response.body.decode())
        finally:
            with server._login_pending_lock:
                server._login_pending = None

    def test_login_pty_timeout_45s_returns_error_and_nukes_container(self) -> None:
        """F-4: when the 45s PTY deadline fires without a URL appearing,
        _handle_login_post returns an error response and nukes the login
        container (TRN-113 / LoginFlowEdgeCaseTests task 7.4)."""
        podman = Mock()
        fake_sock = Mock()
        fake_sock.fileno.return_value = 5
        # recv always returns non-URL content so the URL-extraction loop never breaks.
        fake_sock.recv.return_value = b"Loading...\n"

        with (
            patch.object(server, "_read_auth_file", return_value=""),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_start_login_container", return_value="ga-login-pty45"),
            patch.object(server, "_nuke_login_container") as nuke,
            patch.object(server, "time") as mock_time,
            patch.object(server, "select") as mock_select,
            patch.object(podman, "container_exec", return_value="kiro-cli"),
            patch.object(podman, "container_exec_pty_stdin", return_value=("exec-pty45", fake_sock)),
        ):
            # Simulate: start=1000, first deadline check=1000 (inside loop),
            # second check=1046 (past 45s deadline) — loop exits, error returned.
            mock_time.time.side_effect = [
                1000.0,   # sentinel start timestamp
                1000.0,   # _start_login_container timestamp restore
                1000.0,   # deadline = time.time() + 45.0  -> deadline=1045
                1000.0,   # first while time.time() < deadline (inside loop)
                1046.0,   # second check — past 45s — loop exits
            ]
            mock_select.select.return_value = ([fake_sock], [], [])
            request = Mock()
            response = asyncio.run(server._handle_login_post(request))

        self.assertEqual(response.status_code, 500)
        body = response.body.decode() if isinstance(response.body, bytes) else response.body
        self.assertIn("45s", body)
        nuke.assert_called_once_with(podman, "ga-login-pty45")


# ── AdmiralSecretHardeningTests (TRN-53) ─────────────────────────────────────
#
# Task 4.3: verify that two distinct secrets are generated and policy_signing_key
# (not admiral_secret) is forwarded to the _inject_policy() call.
# Task 4.4: verify that policy_signing_key is stored in the crews.json entry
# when policy injection succeeds.


class AdmiralSecretHardeningTests(unittest.TestCase):
    """TRN-53: admiral_secret and policy_signing_key are distinct; only
    policy_signing_key flows into the policy injection call; and
    crews.json stores policy_signing_key when injection succeeds.
    """

    def _run_finish_crew_setup(
        self,
        inject_policy_calls: list,
        admiral_secret_calls: list,
        policy_injection_ok: bool = True,
    ) -> tuple[dict, dict]:
        """Run lifecycle._finish_crew_setup with enough mocking to reach the
        registry write, capturing _inject_policy call args and the
        inject_admiral_secret.py exec args.

        Returns (registry_data, result) so callers can inspect both.
        """

        class CapturingPodman:
            def container_stop(self, container: str) -> None:
                pass

            def container_start(self, container: str) -> None:
                pass

            def container_exec(
                self, container: str, cmd: list, env: dict | None = None
            ) -> str:
                return "ready"

            def container_exec_checked(self, container: str, cmd: list) -> str:
                return "ok"

            def container_exec_stdin(
                self, container: str, cmd: list, stdin_data: bytes
            ) -> str:
                if "inject_admiral_secret.py" in " ".join(cmd):
                    # Secret is delivered via stdin
                    admiral_secret_calls.append(stdin_data.decode())
                return "admiral secret injected"

            def container_inspect(self, container: str) -> dict:
                return {"Config": {"Labels": {}}}

        podman = CapturingPodman()

        def fake_inject_policy(
            p, container: str, composition: str, policy_signing_key: str
        ) -> str:
            inject_policy_calls.append({
                "container": container,
                "composition": composition,
                "policy_signing_key": policy_signing_key,
            })
            if not policy_injection_ok:
                raise RuntimeError("policy injection deliberately failed")
            return "1"

        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            registry = data_dir / "crews.json"
            with (
                patch.object(_registry_mod, "DATA_DIR", data_dir),
                patch.object(_registry_mod, "REGISTRY_PATH", registry),
                patch.object(lifecycle, "_wait_gateway", return_value=True),
                patch.object(lifecycle, "_inject_auth"),
                patch.object(lifecycle, "_patch_crew_config"),
                patch.object(lifecycle, "_copy_agents"),
                patch.object(lifecycle, "_copy_skills"),
                patch.object(lifecycle, "_copy_steering"),
                patch.object(lifecycle, "_seed_openspec_store"),
                patch.object(lifecycle, "_patch_models"),
                patch.object(lifecycle, "_mint_cookie", return_value="cookie"),
                patch.object(lifecycle, "_inject_policy", side_effect=fake_inject_policy),
            ):
                result = lifecycle._finish_crew_setup(
                    podman,
                    "demo",
                    "gs-demo",
                    "gs-vol-demo",
                    "gs-home-demo",
                    "auth-b64",
                )

            registry_data = json.loads(registry.read_text()) if registry.exists() else {}
        return registry_data, result

    def test_two_distinct_secrets_generated_and_policy_signing_key_forwarded(self) -> None:
        """4.3: policy_signing_key (not admiral_secret) is passed to _inject_policy;
        and the two secrets are distinct values."""
        inject_policy_calls: list = []
        admiral_secret_calls: list = []
        self._run_finish_crew_setup(inject_policy_calls, admiral_secret_calls)

        self.assertEqual(len(inject_policy_calls), 1,
                         "Expected exactly one _inject_policy call")
        self.assertEqual(len(admiral_secret_calls), 1,
                         "Expected exactly one inject_admiral_secret.py exec call")

        forwarded_key = inject_policy_calls[0]["policy_signing_key"]
        admiral_secret_value = admiral_secret_calls[0]

        # The two secrets must be distinct
        self.assertNotEqual(
            forwarded_key,
            admiral_secret_value,
            "policy_signing_key and admiral_secret must be distinct secrets",
        )
        # Both must be non-empty
        self.assertTrue(forwarded_key, "policy_signing_key must be non-empty")
        self.assertTrue(admiral_secret_value, "admiral_secret must be non-empty")

    def test_policy_signing_key_stored_in_registry_when_injection_succeeds(self) -> None:
        """4.4 (TRN-93): crews.json entry contains policy_signing_key_id (identifier) when
        policy injection succeeds, not the plaintext policy_signing_key."""
        inject_policy_calls: list = []
        admiral_secret_calls: list = []
        registry_data, result = self._run_finish_crew_setup(
            inject_policy_calls, admiral_secret_calls, policy_injection_ok=True
        )

        crew_entry = registry_data.get("crews", {}).get("demo", {})
        # TRN-93: plaintext secrets are replaced with non-reversible identifiers.
        self.assertNotIn("policy_signing_key", crew_entry,
                         "crews.json entry must NOT contain plaintext policy_signing_key (TRN-93)")
        self.assertIn("policy_signing_key_id", crew_entry,
                      "crews.json entry must contain policy_signing_key_id on success")
        val = crew_entry["policy_signing_key_id"]
        self.assertTrue(str(val).startswith("sha256:"),
                        f"policy_signing_key_id must be a sha256: identifier, got: {val!r}")

    def test_policy_signing_key_absent_from_registry_when_injection_fails(self) -> None:
        """4.4 (failure path): policy_signing_key is NOT stored when injection fails."""
        inject_policy_calls: list = []
        admiral_secret_calls: list = []
        registry_data, result = self._run_finish_crew_setup(
            inject_policy_calls, admiral_secret_calls, policy_injection_ok=False
        )

        crew_entry = registry_data.get("crews", {}).get("demo", {})
        self.assertNotIn("policy_signing_key", crew_entry,
                         "policy_signing_key must not be stored when injection failed")
        self.assertNotIn("policy_version", crew_entry,
                         "policy_version must not be stored when injection failed")

    # ── TRN-62: _inject_auth skipped when KIRO_API_KEY is set ────────────────

    def _run_finish_setup_capturing_inject_auth(self, api_key: str):
        """Run _finish_crew_setup with lifecycle.KIRO_API_KEY set to api_key,
        returning the _inject_auth Mock so callers can assert on its calls."""

        class CapturingPodman:
            def container_stop(self, container: str) -> None:
                pass

            def container_start(self, container: str) -> None:
                pass

            def container_exec(self, container, cmd, env=None) -> str:
                return "ready"

            def container_exec_checked(self, container, cmd) -> str:
                return "ok"

            def container_exec_stdin(self, container, cmd, stdin_data) -> str:
                return "ok"

            def container_inspect(self, container) -> dict:
                return {"Config": {"Labels": {}}}

        inject_auth = Mock()
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            registry = data_dir / "crews.json"
            with (
                patch.object(_registry_mod, "DATA_DIR", data_dir),
                patch.object(_registry_mod, "REGISTRY_PATH", registry),
                patch.object(lifecycle, "KIRO_API_KEY", api_key),
                patch.object(lifecycle, "_wait_gateway", return_value=True),
                patch.object(lifecycle, "_inject_auth", inject_auth),
                patch.object(lifecycle, "_patch_crew_config"),
                patch.object(lifecycle, "_copy_agents"),
                patch.object(lifecycle, "_copy_skills"),
                patch.object(lifecycle, "_copy_steering"),
                patch.object(lifecycle, "_seed_openspec_store"),
                patch.object(lifecycle, "_patch_models"),
                patch.object(lifecycle, "_mint_cookie", return_value="cookie"),
                patch.object(lifecycle, "_inject_policy", return_value="1"),
            ):
                lifecycle._finish_crew_setup(
                    CapturingPodman(),
                    "demo",
                    "gs-demo",
                    "gs-vol-demo",
                    "gs-home-demo",
                    None if api_key else "auth-b64",
                )
        return inject_auth

    def test_inject_auth_skipped_when_api_key_set(self) -> None:
        """6.1: _finish_crew_setup does NOT call _inject_auth when KIRO_API_KEY
        is set — the crew authenticates via the injected env var instead."""
        inject_auth = self._run_finish_setup_capturing_inject_auth("sk-test-key")
        inject_auth.assert_not_called()

    def test_inject_auth_called_when_api_key_unset(self) -> None:
        """6.2: existing device-code path unchanged — _inject_auth IS called
        when KIRO_API_KEY is unset."""
        inject_auth = self._run_finish_setup_capturing_inject_auth("")
        inject_auth.assert_called_once()


# ── PatchCrewConfigTests (F-2) ───────────────────────────────────────────────
#
# ``_patch_crew_config`` is defined in lifecycle.py → patch lifecycle.X.
# The function calls podman.container_exec with the overrides b64-encoded in
# the last argv position. We capture that call and decode the dict to inspect
# the written values.


class PatchCrewConfigTests(unittest.TestCase):
    """Tests for _patch_crew_config (TRN-113 / F-2)."""

    def _call_patch_crew_config(self) -> dict:
        """Call lifecycle._patch_crew_config with a stub podman that captures
        the container_exec call, then decode and return the agent_overrides dict."""
        import base64
        import json as _json

        exec_calls: list[list[str]] = []

        class CapturingPodman:
            def container_exec(
                self, container: str, cmd: list[str], env: dict | None = None
            ) -> str:
                exec_calls.append(cmd)
                return "patched config.local.json"

        lifecycle._patch_crew_config(CapturingPodman(), "gs-demo")

        self.assertTrue(exec_calls, "container_exec was never called")
        cmd = exec_calls[0]
        # cmd = ["python3", ".../patch_crew_config.py", "<config_path>", "<b64>"]
        overrides_b64 = cmd[-1]
        return _json.loads(base64.b64decode(overrides_b64).decode())

    def test_patch_crew_config_sets_sandbox_off(self) -> None:
        """sandbox must be 'off' -- without it every agent spawn fails under
        rootless Podman because kiro-cli 0.5.0+ is fail-closed on the
        MS_REMOUNT inside a user namespace (TRN-113)."""
        overrides = self._call_patch_crew_config()
        self.assertEqual(
            overrides.get("sandbox"),
            "off",
            f"Expected sandbox='off' but got: {overrides.get('sandbox')!r}",
        )

    def test_patch_crew_config_sets_dangerously_skip_permissions(self) -> None:
        """dangerously_skip_permissions must be True so the transport (different
        UID) can write config.local.json inside the crew container."""
        overrides = self._call_patch_crew_config()
        self.assertIs(
            overrides.get("dangerously_skip_permissions"),
            True,
            f"Expected dangerously_skip_permissions=True but got: "
            f"{overrides.get('dangerously_skip_permissions')!r}",
        )


# ── TRN-108: schedule monitor gateway source-of-truth ────────────────────────


class ScheduleMonitorGatewayTests(unittest.TestCase):
    """TRN-108: _schedule_monitor checks the gateway /api/crons after waking
    the crew; the registry is the fallback, not the authority.

    Strategy: call _schedule_monitor's inner body once by monkey-patching
    ``time.sleep`` (to avoid the infinite outer loop) and patching out the
    parts we don't want to exercise per test.  The function under test
    resolves _crew_api, _crew_api_with_recovery, _load_registry, _save_registry,
    _get_crew_schedules, _ensure_crew_running etc. from lifecycle's namespace,
    so all patches are on ``lifecycle.*`` (call-site principle, design.md §2).
    """

    # Shared fixture helpers ──────────────────────────────────────────────────

    def _sched(self, **overrides: object) -> dict:
        """Minimal schedule entry with sensible defaults."""
        base: dict = {
            "job_id": "job-abc",
            "enabled": True,
            "next_fire_at": 0.0,  # always due
            "message": "tick",
            "agent": "raven",
        }
        base.update(overrides)
        return base

    def _crew_info(self, sched: dict) -> dict:
        return {"container": "gs-demo", "cookie": "cookie", "schedules": [sched]}

    def _registry(self, sched: dict) -> dict:
        return {"crews": {"demo": self._crew_info(sched)}}

    def _run_one_cycle(
        self,
        sched: dict,
        *,
        crew_api_side_effect: object = None,
        crew_api_return_value: object = None,
        ensure_raises: Exception | None = None,
        registry_enabled: bool = True,
    ) -> Mock:
        """Run exactly one iteration of _schedule_monitor's inner loop and
        return the _crew_api_with_recovery mock so tests can assert on it.

        Uses a sentinel exception to break out of the outer ``while True`` loop
        after the first pass through.
        """

        class _BreakLoop(Exception):
            pass

        sched["enabled"] = registry_enabled

        crew_obj = {"container": "gs-demo", "cookie": "cookie"}

        # A reload of the registry inside the loop must reflect our sched.
        def _fake_load_registry() -> dict:
            return self._registry(sched)

        crew_api_mock = Mock()
        if crew_api_side_effect is not None:
            crew_api_mock.side_effect = crew_api_side_effect
        elif crew_api_return_value is not None:
            crew_api_mock.return_value = crew_api_return_value

        spawn_mock = Mock()

        sleep_calls = [0]

        def _fake_sleep(n: float) -> None:
            sleep_calls[0] += 1
            if sleep_calls[0] > 1:
                raise _BreakLoop

        ensure_mock = Mock()
        if ensure_raises:
            ensure_mock.side_effect = ensure_raises
        else:
            ensure_mock.return_value = crew_obj

        save_mock = Mock()

        with (
            patch.object(lifecycle, "time") as time_mock,
            patch.object(lifecycle, "_load_registry", side_effect=_fake_load_registry),
            patch.object(lifecycle, "_save_registry", save_mock),
            patch.object(lifecycle, "_get_crew_schedules", return_value=[sched]),
            patch.object(lifecycle, "_ensure_crew_running", ensure_mock),
            patch.object(lifecycle, "_crew_api", crew_api_mock),
            patch.object(lifecycle, "_crew_api_with_recovery", spawn_mock),
            patch.object(lifecycle, "_advance_next_fire_at"),
        ):
            time_mock.sleep.side_effect = _fake_sleep
            time_mock.time.return_value = 9999.0  # always past next_fire_at=0
            try:
                lifecycle._schedule_monitor()
            except _BreakLoop:
                pass

        return spawn_mock, crew_api_mock, save_mock

    # ── 3.1: gateway disabled → skip and write back ───────────────────────────

    def test_gateway_disabled_skips_fire_and_writes_back(self) -> None:
        """3.1: when /api/crons reports enabled=false, spawn is not called and
        the registry entry is updated to enabled=false."""
        sched = self._sched()
        cron_payload = {"jobs": [{"id": "job-abc", "enabled": False}]}
        spawn_mock, _, save_mock = self._run_one_cycle(
            sched, crew_api_return_value=cron_payload
        )
        spawn_mock.assert_not_called()
        # save_registry must have been called (write-back)
        self.assertTrue(save_mock.called, "expected _save_registry to be called")
        # The sched dict in the registry should have been mutated to enabled=False
        self.assertFalse(sched.get("enabled"), "registry entry must be set to enabled=False")

    # ── 3.2: gateway enabled → fire normally ─────────────────────────────────

    def test_gateway_enabled_fires_normally(self) -> None:
        """3.2: when /api/crons reports enabled=true, spawn IS called."""
        sched = self._sched()
        cron_payload = {"jobs": [{"id": "job-abc", "enabled": True}]}
        spawn_mock, _, _ = self._run_one_cycle(
            sched, crew_api_return_value=cron_payload
        )
        spawn_mock.assert_called_once()

    # ── 3.3: job absent from gateway listing → fire (fail-open) ─────────────

    def test_gateway_missing_job_fires_normally(self) -> None:
        """3.3: when /api/crons returns no matching job_id, spawn IS called
        (fail-open — unknown job is treated as enabled)."""
        sched = self._sched()
        cron_payload = {"jobs": []}  # no jobs at all
        spawn_mock, _, _ = self._run_one_cycle(
            sched, crew_api_return_value=cron_payload
        )
        spawn_mock.assert_called_once()

    # ── 3.4: gateway raises + registry disabled → skip ──────────────────────

    def test_gateway_raises_registry_disabled_skips(self) -> None:
        """3.4: when _crew_api raises AND registry has enabled=false, spawn is
        NOT called — the registry fallback is honoured."""
        sched = self._sched(enabled=False)
        spawn_mock, _, _ = self._run_one_cycle(
            sched,
            crew_api_side_effect=RuntimeError("connection refused"),
            registry_enabled=False,
        )
        # The top-of-loop fast-path sched.get("enabled", True) is False → continue
        # before _ensure_crew_running is even reached.
        spawn_mock.assert_not_called()

    # ── 3.5: gateway raises + registry enabled → fire (fail-open) ────────────

    def test_gateway_raises_registry_enabled_fires(self) -> None:
        """3.5: when _crew_api raises AND registry has enabled=true (or absent),
        spawn IS called — fail-open fallback to registry."""
        sched = self._sched()
        spawn_mock, _, _ = self._run_one_cycle(
            sched,
            crew_api_side_effect=RuntimeError("network timeout"),
        )
        spawn_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
