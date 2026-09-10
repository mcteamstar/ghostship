"""Unit + REST tests for the ACP prewarm operation (TRN-131).

Covers ``lifecycle._prewarm_crew`` / ``lifecycle.prewarm`` (the transport-side
warm-up mechanism) and the ``POST /crews/{crew_id}/prewarm`` REST surface via
``server._handle_crew_prewarm_post`` + ``BearerAuthMiddleware``.

Patch-target rule (test_lifecycle §2, the call-site principle):

* ``_prewarm_crew`` / ``prewarm`` are defined in ``lifecycle.py`` and resolve
  ``_ensure_crew_running`` / ``_crew_api_with_recovery`` / ``_require_crew`` /
  ``_get_podman`` and the ``GA_PREWARM_*`` constants from lifecycle's globals,
  so those are patched ``lifecycle.X``.
* ``_handle_crew_prewarm_post`` is defined in ``server.py`` and resolves
  ``_resolve_crew_for_proxy`` / ``_prewarm_crew`` from server's namespace, so
  those call sites are patched ``server.X``.
"""

from __future__ import annotations

import asyncio
import json
import threading
import unittest
from unittest.mock import patch

from tests.unit.helpers import lifecycle, server


class _FakeStreamRequest:
    """Minimal async-compatible request stub for the REST handler test."""

    def __init__(self, method: str = "POST", path: str = "/crews/demo/prewarm") -> None:
        self.method = method
        self.scope = {"type": "http", "method": method, "path": path, "query_string": b""}
        self.headers = {}

    async def body(self) -> bytes:
        return b""


class _FakeDownstream:
    """ASGI app that records whether the inner app was reached (auth passthrough)."""

    def __init__(self) -> None:
        self.called = False

    async def __call__(self, scope, receive, send) -> None:
        self.called = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"OK"})


def _run_asgi(app, scope, body: bytes = b"") -> tuple[int, list, bytes]:
    status = None
    resp_headers: list = []
    resp_body = b""

    async def receive():
        return {"type": "http.request", "body": body}

    async def send(msg):
        nonlocal status, resp_headers, resp_body
        if msg["type"] == "http.response.start":
            status = msg["status"]
            resp_headers = msg.get("headers", [])
        elif msg["type"] == "http.response.body":
            resp_body += msg.get("body", b"")

    asyncio.run(app(scope, receive, send))
    return status, resp_headers, resp_body


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


class PrewarmDisabledTests(unittest.TestCase):
    """4.1 — disabled returns ``disabled`` and performs no start/fork."""

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


class PrewarmStoppedCrewTests(unittest.TestCase):
    """4.2 — stopped crew (gates permitting) starts, waits, warms once, warmed."""

    def setUp(self) -> None:
        with lifecycle._warm_markers_lock:
            lifecycle._warm_markers.clear()

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
        # Exactly one warm-up request, routed through the recovery wrapper.
        self.assertEqual(warmup.call_count, 1)
        call = warmup.call_args
        self.assertEqual(call.args[0], warmed_crew)
        self.assertEqual(call.args[1], "demo")
        self.assertEqual(call.args[2], "GET")
        self.assertEqual(call.args[3], lifecycle._PREWARM_WARMUP_PATH)
        # A warm marker was recorded.
        with lifecycle._warm_markers_lock:
            self.assertIn("demo", lifecycle._warm_markers)


class PrewarmAlreadyWarmTests(unittest.TestCase):
    """4.3 — running crew with a fresh marker returns already_warm, no rework."""

    def setUp(self) -> None:
        with lifecycle._warm_markers_lock:
            lifecycle._warm_markers.clear()

    def test_already_warm_no_restart_no_second_warmup(self) -> None:
        crew = {"container": "gs-demo", "cookie": "c"}
        podman = _RecordingPodman(running=True)
        import time as _time
        with lifecycle._warm_markers_lock:
            lifecycle._warm_markers["demo"] = _time.monotonic()
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
        self.assertEqual(podman.starts, [])


class PrewarmNonDestructiveTests(unittest.TestCase):
    """4.4 — no /api/spawn real-task dispatch, no mail, no spec/workspace write."""

    def setUp(self) -> None:
        with lifecycle._warm_markers_lock:
            lifecycle._warm_markers.clear()

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
        # Non-destructive: GET readiness/session surface, never POST /api/spawn.
        self.assertEqual(method, "GET")
        self.assertNotIn("/api/spawn", path)
        self.assertNotIn("json", kw)  # no task body / real-work payload
        self.assertEqual(lifecycle._PREWARM_WARMUP_PATH, path)


class PrewarmGateTests(unittest.TestCase):
    """4.5 — memory + active-crew gates each produce blocked:<gate>, no start."""

    def setUp(self) -> None:
        with lifecycle._warm_markers_lock:
            lifecycle._warm_markers.clear()

    def _run_with_gate(self, error: RuntimeError) -> dict:
        crew = {"container": "gs-demo", "cookie": "c"}
        podman = _RecordingPodman(running=False)
        with (
            patch.object(lifecycle, "GA_PREWARM_ENABLED", True),
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(lifecycle, "_ensure_crew_running", side_effect=error),
            patch.object(lifecycle, "_crew_api_with_recovery") as warmup,
        ):
            result = lifecycle._prewarm_crew(crew, "demo")
        self.assertFalse(warmup.called)
        return result

    def test_memory_gate_blocks(self) -> None:
        result = self._run_with_gate(
            RuntimeError("Insufficient available memory to start crew demo: 1.0GB free")
        )
        self.assertEqual(result, {"crew_id": "demo", "status": "blocked:insufficient-memory"})

    def test_active_crew_gate_blocks(self) -> None:
        result = self._run_with_gate(
            RuntimeError("Active crew limit (3) reached — wait for a running crew to idle out")
        )
        self.assertEqual(result, {"crew_id": "demo", "status": "blocked:active-crew-limit"})


class PrewarmTtlCapTests(unittest.TestCase):
    """4.6 — warm marker TTL is capped at session.timeout_secs."""

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
        """A marker older than the capped TTL does not count as already_warm."""
        with lifecycle._warm_markers_lock:
            lifecycle._warm_markers.clear()
        crew = {"container": "gs-demo", "cookie": "c"}
        podman = _RecordingPodman(running=True)
        import time as _time
        # Marker is 400s old; capped TTL is 300s → stale → must rewarm.
        with lifecycle._warm_markers_lock:
            lifecycle._warm_markers["demo"] = _time.monotonic() - 400
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


class PrewarmUnknownCrewTests(unittest.TestCase):
    """4.7 — unknown crew_id returns an error and takes no action."""

    def test_unknown_crew_returns_error_no_action(self) -> None:
        with (
            patch.object(lifecycle, "_require_crew", side_effect=ValueError("crew_id required")),
            patch.object(lifecycle, "_ensure_crew_running") as ensure,
            patch.object(lifecycle, "_crew_api_with_recovery") as warmup,
        ):
            result = lifecycle.prewarm("nope")

        self.assertIn("error", result)
        ensure.assert_not_called()
        warmup.assert_not_called()


class PrewarmWarmupErrorTests(unittest.TestCase):
    """2.6 — a warm-up request failure yields error:<msg>, dispatch unchanged."""

    def setUp(self) -> None:
        with lifecycle._warm_markers_lock:
            lifecycle._warm_markers.clear()

    def test_warmup_failure_returns_error_status(self) -> None:
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


class PrewarmRestEndpointTests(unittest.TestCase):
    """4.8 — REST endpoint succeeds with valid GA_API_KEY, rejected without it."""

    def test_handler_returns_status_json(self) -> None:
        crew = {"container": "gs-demo", "cookie": "c"}

        async def fake_resolve(path, auto_wake=True):
            return ("demo", "", crew)

        async def run():
            with (
                patch.object(server, "_resolve_crew_for_proxy", side_effect=fake_resolve),
                patch.object(
                    server, "_prewarm_crew",
                    return_value={"crew_id": "demo", "status": "warmed"},
                ),
            ):
                request = _FakeStreamRequest(method="POST", path="/crews/demo/prewarm")
                return await server._handle_crew_prewarm_post(request)

        response = asyncio.run(run())
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertEqual(body, {"crew_id": "demo", "status": "warmed"})

    def test_handler_404_for_unknown_crew(self) -> None:
        async def fake_resolve(path, auto_wake=True):
            return server.PlainTextResponse("Crew 'nope' not found", status_code=404)

        async def run():
            with patch.object(server, "_resolve_crew_for_proxy", side_effect=fake_resolve):
                request = _FakeStreamRequest(method="POST", path="/crews/nope/prewarm")
                return await server._handle_crew_prewarm_post(request)

        response = asyncio.run(run())
        self.assertEqual(response.status_code, 404)

    def test_middleware_dispatches_prewarm_when_auth_passes(self) -> None:
        handled = []

        async def fake_prewarm_post(req):
            handled.append("prewarm")
            return server.PlainTextResponse("ok")

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/crews/demo/prewarm",
            "headers": [(b"authorization", b"Bearer testkey")],
        }
        mw = server.BearerAuthMiddleware(
            _FakeDownstream(), api_key="testkey",
            routes={("POST", "/crews/*/prewarm"): fake_prewarm_post},
        )
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 200)
        self.assertIn("prewarm", handled)

    def test_middleware_rejects_prewarm_when_key_missing(self) -> None:
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/crews/demo/prewarm",
            "headers": [],  # no Authorization header
        }
        mw = server.BearerAuthMiddleware(_FakeDownstream(), api_key="secret")
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 401)

    def test_middleware_rejects_prewarm_when_key_wrong(self) -> None:
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/crews/demo/prewarm",
            "headers": [(b"authorization", b"Bearer wrongkey")],
        }
        mw = server.BearerAuthMiddleware(_FakeDownstream(), api_key="correctkey")
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
