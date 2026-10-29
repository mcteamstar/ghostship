"""Extended e2e tests — error paths, schedule/steer tools, response schemas.

Extends the smoke suite. Same skip guard: set GHOSTSHIP_E2E_URL
to a live transport to run, unset to skip cleanly.

    GHOSTSHIP_E2E_URL=http://your-academy-host bash scripts/run.sh --e2e
"""

import os
import time
import unittest

import httpx2 as httpx

from tests.e2e.helpers import (
    GHOSTSHIP_E2E_URL,
    GHOSTSHIP_API_KEY,
    GHOSTSHIP_PODMAN_SOCKET,
    _SKIP_REASON,
    _TRANSPORT_REACHABLE,
    mcp_call as _mcp_call,
    is_error as _is_error,
    container_stop as _container_stop,
    container_is_running as _container_is_running,
    wait_until_stopped as _wait_until_stopped,
)

# ── Module-level shared crew ──────────────────────────────────────────────────
# TestErrorPaths (stateless tests), TestScheduleTool, and TestResponseSchemas
# all share this crew. It is launched once per file (setUpModule) and torn
# down once (tearDownModule). TestSteerTool keeps its own crew for isolation.
# TestCaptainStatusStoppedCrew keeps its own crew because it stops it via Podman.

SHARED_CREW_ID = "e2e-shared-ext"

# Module-level launch result — stored so TestResponseSchemas.test_launch_response_shape
# can assert on launch shape without triggering a second launch.
_SHARED_LAUNCH_RESULT: dict = {}


def setUpModule():  # noqa: N802
    if not _TRANSPORT_REACHABLE:
        return  # all classes skip via @skipUnless anyway
    try:
        _mcp_call("nuke", crew_id=SHARED_CREW_ID, confirm=True)
    except Exception:
        pass
    result = _mcp_call("launch", crew_id=SHARED_CREW_ID)
    _SHARED_LAUNCH_RESULT.update(result)
    if result.get("status") != "ready":
        raise RuntimeError(f"setUpModule: failed to launch {SHARED_CREW_ID}: {result}")


def tearDownModule():  # noqa: N802
    try:
        _mcp_call("nuke", crew_id=SHARED_CREW_ID, confirm=True)
    except Exception:
        pass


# ── 1. Error paths ────────────────────────────────────────────────────────────


@unittest.skipUnless(_TRANSPORT_REACHABLE, _SKIP_REASON)
class TestErrorPaths(unittest.TestCase):
    """Non-happy-path calls should return structured errors, never 500."""

    # Retained constant for the three non-existent-crew tests below, which need
    # no live crew: test_nuke_nonexistent_crew, test_dispatch_nonexistent_crew,
    # test_evac_nonexistent_crew.
    GHOST_CREW = "e2e-does-not-exist"

    # Stateless tests use the module-level shared crew.
    CREW_ID = SHARED_CREW_ID

    def test_nuke_nonexistent_crew(self):
        result = _mcp_call("nuke", crew_id=self.GHOST_CREW, confirm=True)
        self.assertTrue(_is_error(result), f"Expected error, got: {result}")
        self.assertIn("not found", result["error"].lower())

    def test_dispatch_nonexistent_crew(self):
        result = _mcp_call(
            "dispatch", crew_id=self.GHOST_CREW, task="test", agent="ghost"
        )
        self.assertTrue(_is_error(result), f"Expected error, got: {result}")
        self.assertIn("not found", result["error"].lower())

    def test_evac_nonexistent_crew(self):
        result = _mcp_call("evac", crew_id=self.GHOST_CREW, path="repo/nope.txt")
        self.assertTrue(_is_error(result), f"Expected error, got: {result}")
        self.assertIn("not found", result["error"].lower())

    def test_pickup_nonexistent_task(self):
        # Need a real crew to test a missing task_id within it
        crew_id = "e2e-err-pickup"
        try:
            _mcp_call("nuke", crew_id=crew_id, confirm=True)
        except Exception:
            pass
        launch = _mcp_call("launch", crew_id=crew_id)
        self.assertEqual(launch.get("status"), "ready")
        try:
            result = _mcp_call("pickup", crew_id=crew_id, task_id="00000000")
            self.assertTrue(_is_error(result), f"Expected error, got: {result}")
        finally:
            _mcp_call("nuke", crew_id=crew_id, confirm=True)

    def test_launch_duplicate_crew(self):
        crew_id = "e2e-err-dup"
        try:
            _mcp_call("nuke", crew_id=crew_id, confirm=True)
        except Exception:
            pass
        launch1 = _mcp_call("launch", crew_id=crew_id)
        self.assertEqual(launch1.get("status"), "ready")
        try:
            launch2 = _mcp_call("launch", crew_id=crew_id)
            self.assertTrue(_is_error(launch2), f"Expected error on duplicate, got: {launch2}")
            self.assertIn("already exists", launch2["error"].lower())
        finally:
            _mcp_call("nuke", crew_id=crew_id, confirm=True)

    def test_nuke_without_confirm(self):
        # nuke without confirm=True returns a dry-run warning (not an error),
        # listing what would be destroyed without actually nuking
        crew_id = "e2e-err-noconfirm"
        try:
            _mcp_call("nuke", crew_id=crew_id, confirm=True)
        except Exception:
            pass
        _mcp_call("launch", crew_id=crew_id)
        try:
            result = _mcp_call("nuke", crew_id=crew_id, confirm=False)
            # Should return a warning preview, not nuke the crew
            self.assertFalse(_is_error(result), f"Unexpected error: {result}")
            self.assertIn("warning", result, f"Expected warning in dry-run response: {result}")
            # Crew should still be alive
            crews = _mcp_call("crews")
            crew_ids = [c["crew_id"] for c in crews.get("crews", [])]
            self.assertIn(crew_id, crew_ids, "Crew was nuked despite confirm=False")
        finally:
            _mcp_call("nuke", crew_id=crew_id, confirm=True)


# ── 2. Schedule tool ──────────────────────────────────────────────────────────


@unittest.skipUnless(_TRANSPORT_REACHABLE, _SKIP_REASON)
class TestScheduleTool(unittest.TestCase):
    CREW_ID = SHARED_CREW_ID

    def test_create_list_cancel(self):
        # Create a job
        created = _mcp_call(
            "schedule",
            action="create",
            crew_id=self.CREW_ID,
            name="e2e-test-job",
            message="echo e2e",
            interval=300,
            fire_immediately=False,
        )
        self.assertFalse(_is_error(created), f"Create failed: {created}")
        job_id = created.get("job_id")
        self.assertIsNotNone(job_id, f"No job_id in: {created}")

        # Verify it appears in list
        listed = _mcp_call("schedule", action="list", crew_id=self.CREW_ID)
        self.assertFalse(_is_error(listed), f"List failed: {listed}")
        job_ids = [j["job_id"] for j in listed.get("jobs", [])]
        self.assertIn(job_id, job_ids, f"Job {job_id} not in list: {job_ids}")

        # Cancel it
        cancelled = _mcp_call("schedule", action="cancel", crew_id=self.CREW_ID, job_id=job_id)
        self.assertFalse(_is_error(cancelled), f"Cancel failed: {cancelled}")

        # Verify it's gone
        listed_after = _mcp_call("schedule", action="list", crew_id=self.CREW_ID)
        job_ids_after = [j["job_id"] for j in listed_after.get("jobs", [])]
        self.assertNotIn(job_id, job_ids_after, f"Job still present after cancel: {job_ids_after}")

    def test_cancel_nonexistent_job(self):
        # Cancelling a non-existent job_id is idempotent — returns cancelled, not an error
        result = _mcp_call(
            "schedule", action="cancel", crew_id=self.CREW_ID, job_id="00000000"
        )
        self.assertFalse(_is_error(result), f"Unexpected error: {result}")
        self.assertEqual(result.get("status"), "cancelled")


# ── 3. Steer tool ─────────────────────────────────────────────────────────────


@unittest.skipUnless(_TRANSPORT_REACHABLE, _SKIP_REASON)
class TestSteerTool(unittest.TestCase):
    # Dedicated crew — steers a long-running task; sharing would make
    # task-list assertions ambiguous.
    CREW_ID = "e2e-steer"

    @classmethod
    def setUpClass(cls):
        try:
            _mcp_call("nuke", crew_id=cls.CREW_ID, confirm=True)
        except Exception:
            pass
        print(f"\n[e2e] setUpClass: launching {cls.CREW_ID}...", flush=True)
        result = _mcp_call("launch", crew_id=cls.CREW_ID)
        if result.get("status") != "ready":
            raise RuntimeError(f"Failed to launch {cls.CREW_ID}: {result}")
        print(f"[e2e] {cls.CREW_ID} ready", flush=True)

    @classmethod
    def tearDownClass(cls):
        try:
            _mcp_call("nuke", crew_id=cls.CREW_ID, confirm=True)
        except Exception:
            pass

    def _wait(self, task_id, until, timeout):
        deadline = time.time() + timeout
        status = {}
        while time.time() < deadline:
            status = _mcp_call("pickup", crew_id=self.CREW_ID, task_id=task_id)
            if until(status):
                return status
            time.sleep(3)
        self.fail(f"Task {task_id} did not reach the expected state in {timeout}s: {status}")

    def test_steer_running_task_changes_course(self):
        # A run of separate tool calls keeps the task mid-turn long enough to
        # steer it, and gives the agent a point between calls to act on it.
        dispatch = _mcp_call(
            "dispatch",
            crew_id=self.CREW_ID,
            agent="ghost",
            task=(
                "Run `sleep 8` with the shell tool, 10 times, as 10 separate tool "
                "calls (never combine them). After each call, say which number call "
                "it was. If you receive a new instruction, follow it."
            ),
        )
        task_id = dispatch.get("task_id")
        self.assertIsNotNone(task_id)

        # Steer only once the agent is really working (a tool has run). Elapsed
        # time alone isn't enough: a kiro session can take minutes to start,
        # and a steer before then is refused with session_starting.
        print(f"[e2e] waiting for task {task_id} to make a tool call...", flush=True)
        self._wait(task_id, lambda s: s.get("done") or s.get("last_tool"), timeout=300)

        token = f"STEERED-{task_id[:6].upper()}"
        message = f"New instruction: stop the sleep calls now and reply with exactly {token}."
        steer_result = _mcp_call("steer", task_id=task_id, crew_id=self.CREW_ID, message=message)
        self.assertFalse(_is_error(steer_result), f"Steer returned error: {steer_result}")
        action = steer_result.get("action")
        self.assertIn(action, ("steered", "follow_up_queued", "redeployed"), steer_result)
        print(f"[e2e] steer action: {action}", flush=True)

        # The agent must act on the message, not just have it accepted: a 200
        # that was silently dropped is what hid this bug before.
        if action == "redeployed":
            # The task finished before the steer landed, so steer continued its
            # session as a new task; that task must carry the instruction out.
            result = self._wait(steer_result["task_id"], lambda s: s.get("done"), timeout=180)
            self.assertIn(token, result.get("result", ""), f"Continuation was not acted on: {result}")
            return
        final = self._wait(task_id, lambda s: s.get("done"), timeout=300)
        if action == "steered":
            self.assertIn(token, final.get("result", ""), f"Interrupt steer was not acted on: {final}")
            return

        # follow_up_queued: the message runs as a new continuation task once
        # the original turn ends.
        deadline = time.time() + 120
        follow_up = None
        while time.time() < deadline and follow_up is None:
            listing = _mcp_call("pickup", crew_id=self.CREW_ID)
            follow_up = next(
                (t for t in listing.get("tasks", []) if t.get("task", "").startswith(message[:60])),
                None,
            )
            if follow_up is None:
                time.sleep(3)
        self.assertIsNotNone(follow_up, "Follow-up continuation task never appeared")
        result = self._wait(follow_up["task_id"], lambda s: s.get("done"), timeout=180)
        self.assertIn(token, result.get("result", ""), f"Follow-up was not acted on: {result}")

    def test_steer_nonexistent_task(self):
        result = _mcp_call(
            "steer",
            task_id="00000000",
            crew_id=self.CREW_ID,
            message="hello",
        )
        self.assertTrue(_is_error(result), f"Expected error steering nonexistent task: {result}")


# ── 4. Response schemas ───────────────────────────────────────────────────────


@unittest.skipUnless(_TRANSPORT_REACHABLE, _SKIP_REASON)
class TestResponseSchemas(unittest.TestCase):
    """Verify all expected fields are present on tool responses."""

    CREW_ID = SHARED_CREW_ID
    _CREW_FIELDS = {
        "crew_id", "container", "status", "composition",
        "created_at", "gateway_healthy", "crew_image_version",
        "agents", "policy_version",
    }

    def test_launch_response_shape(self):
        # Assert on the module-level launch result — no second crew launch needed.
        result = _SHARED_LAUNCH_RESULT
        self.assertEqual(result.get("crew_id"), SHARED_CREW_ID)
        self.assertEqual(result.get("status"), "ready")
        self.assertIn("container", result)
        self.assertIn("gateway_url", result)

    def test_crews_response_shape(self):
        result = _mcp_call("crews")
        self.assertIn("crews", result)
        self.assertIn("active_crews", result)
        self.assertIn("max_active_crews", result)
        self.assertIn("host_memory_available_gb", result)

        # Every crew object must have all required fields
        for crew in result["crews"]:
            missing = self._CREW_FIELDS - set(crew.keys())
            self.assertFalse(missing, f"Crew {crew.get('crew_id')} missing fields: {missing}")

    def test_dispatch_response_shape(self):
        result = _mcp_call(
            "dispatch",
            crew_id=self.CREW_ID,
            agent="ghost",
            task="Say hello.",
        )
        self.assertFalse(_is_error(result), f"Dispatch error: {result}")
        for field in ("task_id", "crew_id", "status", "agent"):
            self.assertIn(field, result, f"Missing field {field!r} in dispatch response")
        self.assertEqual(result["crew_id"], self.CREW_ID)
        self.assertEqual(result["status"], "dispatched")

    def test_pickup_list_shape(self):
        # pickup without task_id returns a task list
        result = _mcp_call("pickup", crew_id=self.CREW_ID)
        self.assertFalse(_is_error(result), f"Pickup list error: {result}")
        self.assertIn("tasks", result)
        self.assertIn("mail_summary", result)

    def test_supply_response_shape(self):
        result = _mcp_call("supply", crew_id=self.CREW_ID, path="repo/test.txt")
        self.assertFalse(_is_error(result), f"Supply error: {result}")
        for field in ("crew_id", "path", "delivery_url", "method", "expires_secs"):
            self.assertIn(field, result, f"Missing field {field!r} in supply response")
        self.assertEqual(result["method"], "POST")


# ── 5. Auth extended (requires GHOSTSHIP_API_KEY) ─────────────────────────────


@unittest.skipUnless(
    GHOSTSHIP_E2E_URL and GHOSTSHIP_API_KEY,
    "GHOSTSHIP_E2E_URL and GHOSTSHIP_API_KEY both required",
)
class TestAuthExtended(unittest.TestCase):
    """Verify auth gate applies across all major tools, not just /health."""

    def _unauthed_post(self, tool: str, **kwargs) -> httpx.Response:
        return httpx.post(
            f"{GHOSTSHIP_E2E_URL}/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": tool, "arguments": kwargs},
                "id": 1,
            },
            headers={"Content-Type": "application/json"},
            timeout=10.0,
        )

    def test_launch_requires_auth(self):
        resp = self._unauthed_post("launch", crew_id="e2e-auth-test")
        self.assertEqual(resp.status_code, 401)

    def test_dispatch_requires_auth(self):
        resp = self._unauthed_post(
            "dispatch", crew_id="e2e-auth-test", task="test", agent="ghost"
        )
        self.assertEqual(resp.status_code, 401)

    def test_nuke_requires_auth(self):
        resp = self._unauthed_post("nuke", crew_id="e2e-auth-test", confirm=True)
        self.assertEqual(resp.status_code, 401)


# ── 6. Captain status on stopped crew ─────────────────────────────────────────


@unittest.skipUnless(_TRANSPORT_REACHABLE, _SKIP_REASON)
@unittest.skipUnless(
    os.path.exists(GHOSTSHIP_PODMAN_SOCKET),
    f"GHOSTSHIP_PODMAN_SOCKET not reachable at {GHOSTSHIP_PODMAN_SOCKET} — "
    "set GHOSTSHIP_PODMAN_SOCKET to the transport's Podman socket path or run on the transport host",
)
class TestCaptainStatusStoppedCrew(unittest.TestCase):
    """captain status works on stopped crews without waking them.

    Requires a live transport at GHOSTSHIP_E2E_URL and a reachable Podman
    socket at GHOSTSHIP_PODMAN_SOCKET. The test launches a crew, stops the
    container directly via the Podman REST API (not via captain stop, which
    only pauses the cron job), and asserts that captain(action="status")
    returns HTTP 200 with subject arrays present and the container still
    stopped after the call.

    Crew name: e2e-trn51-captain-stopped — nuked on teardown.
    """

    CREW_ID = "e2e-trn51-captain-stopped"
    # Container name mirrors the transport's naming: CREW_CONTAINER_PREFIX + crew_id
    CONTAINER = f"gs-{CREW_ID}"

    @classmethod
    def setUpClass(cls) -> None:
        """Launch a crew, then stop its container via Podman so it is genuinely stopped."""
        try:
            _mcp_call("nuke", crew_id=cls.CREW_ID, confirm=True)
        except Exception:
            pass
        result = _mcp_call("launch", crew_id=cls.CREW_ID)
        if result.get("status") != "ready":
            raise RuntimeError(f"Failed to launch {cls.CREW_ID}: {result}")

        # Stop the container directly via Podman — captain stop only pauses the
        # cron job and does not stop the container, so it is not sufficient here.
        _container_stop(cls.CONTAINER)
        stopped = _wait_until_stopped(cls.CONTAINER, timeout=30)
        if not stopped:
            raise RuntimeError(
                f"Container {cls.CONTAINER} did not stop within 30s"
            )

    @classmethod
    def tearDownClass(cls) -> None:
        """Tear down the test crew."""
        try:
            _mcp_call("nuke", crew_id=cls.CREW_ID, confirm=True)
        except Exception:
            pass

    def test_captain_status_stopped_crew_returns_200_with_subjects(self) -> None:
        """Captain status on a stopped crew returns HTTP 200 and subject arrays."""
        result = _mcp_call("captain", crew_id=self.CREW_ID, action="status")
        self.assertFalse(_is_error(result), f"captain status returned error: {result}")
        # Subject arrays must be present (may be empty on a fresh crew)
        self.assertIn("captain_subjects", result, "captain_subjects missing from status response")
        self.assertIn("admiral_subjects", result, "admiral_subjects missing from status response")
        self.assertIsInstance(result["captain_subjects"], list)
        self.assertIsInstance(result["admiral_subjects"], list)

    def test_captain_status_does_not_start_stopped_container(self) -> None:
        """Captain status must not start the container on a stopped crew."""
        # Confirm the container is still stopped before the call (setup guarantee)
        self.assertFalse(
            _container_is_running(self.CONTAINER),
            f"Pre-condition failed: {self.CONTAINER} was already running before captain status",
        )
        # Call captain status
        _mcp_call("captain", crew_id=self.CREW_ID, action="status")
        # The container must still be stopped — check via Podman directly so we
        # don't rely on the MCP crews() listing, which only surfaces running crews.
        self.assertFalse(
            _container_is_running(self.CONTAINER),
            f"Crew {self.CREW_ID} container was started by captain status",
        )


if __name__ == "__main__":
    unittest.main()
