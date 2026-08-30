"""Extended e2e tests — error paths, schedule/steer tools, response schemas.

Extends the smoke suite from TRN-79. Same skip guard: set GHOSTSHIP_E2E_URL
to a live transport to run, unset to skip cleanly.

    GHOSTSHIP_E2E_URL=http://your-academy-host bash tests/run.sh --e2e
"""

import os
import time
import unittest

import httpx

from tests.e2e.helpers import GHOSTSHIP_E2E_URL, GHOSTSHIP_API_KEY, _SKIP_REASON, mcp_call as _mcp_call, is_error as _is_error

# ── Helpers ───────────────────────────────────────────────────────────────────
# _mcp_call and _is_error imported from helpers.py


# ── 1. Error paths ────────────────────────────────────────────────────────────


@unittest.skipUnless(GHOSTSHIP_E2E_URL, _SKIP_REASON)
class TestErrorPaths(unittest.TestCase):
    """Non-happy-path calls should return structured errors, never 500."""

    GHOST_CREW = "e2e-does-not-exist"

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


@unittest.skipUnless(GHOSTSHIP_E2E_URL, _SKIP_REASON)
class TestScheduleTool(unittest.TestCase):
    CREW_ID = "e2e-schedule"

    def setUp(self):
        try:
            _mcp_call("nuke", crew_id=self.CREW_ID, confirm=True)
        except Exception:
            pass
        print(f"\n[e2e] setUp: launching {self.CREW_ID}...", flush=True)
        result = _mcp_call("launch", crew_id=self.CREW_ID)
        self.assertEqual(result.get("status"), "ready")
        print(f"[e2e] {self.CREW_ID} ready", flush=True)

    def tearDown(self):
        try:
            _mcp_call("nuke", crew_id=self.CREW_ID, confirm=True)
        except Exception:
            pass

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


@unittest.skipUnless(GHOSTSHIP_E2E_URL, _SKIP_REASON)
class TestSteerTool(unittest.TestCase):
    CREW_ID = "e2e-steer"

    def setUp(self):
        try:
            _mcp_call("nuke", crew_id=self.CREW_ID, confirm=True)
        except Exception:
            pass
        print(f"\n[e2e] setUp: launching {self.CREW_ID}...", flush=True)
        result = _mcp_call("launch", crew_id=self.CREW_ID)
        self.assertEqual(result.get("status"), "ready")
        print(f"[e2e] {self.CREW_ID} ready", flush=True)

    def tearDown(self):
        try:
            _mcp_call("nuke", crew_id=self.CREW_ID, confirm=True)
        except Exception:
            pass

    def test_steer_running_task_returns_ok(self):
        # Dispatch a task that will definitely still be running when we steer it.
        # Using pickup with timeout_secs polls the gateway — the task won't
        # complete before our steer call since it has to start the agent first.
        dispatch = _mcp_call(
            "dispatch",
            crew_id=self.CREW_ID,
            agent="ghost",
            task="Wait 60 seconds before doing anything, then say DONE.",
        )
        task_id = dispatch.get("task_id")
        self.assertIsNotNone(task_id)

        # Poll until the task is actually running (done=false, elapsed > 0)
        print(f"[e2e] waiting for task {task_id} to start...", flush=True)
        deadline = time.time() + 30
        started = False
        while time.time() < deadline:
            status = _mcp_call("pickup", crew_id=self.CREW_ID, task_id=task_id)
            if not status.get("done") and status.get("elapsed_secs", 0) > 0:
                print(f"[e2e] task running ({status.get('elapsed_secs')}s), steering...", flush=True)
                started = True
                break
            time.sleep(2)

        self.assertTrue(started, f"Task {task_id} never started within 30s")

        # Steer — verify the transport accepted the call with the right shape
        steer_result = _mcp_call(
            "steer",
            task_id=task_id,
            crew_id=self.CREW_ID,
            message="Actually just say DONE immediately.",
        )
        self.assertFalse(_is_error(steer_result), f"Steer returned error: {steer_result}")
        self.assertIn("task_id", steer_result, f"No task_id in steer response: {steer_result}")

    def test_steer_nonexistent_task(self):
        result = _mcp_call(
            "steer",
            task_id="00000000",
            crew_id=self.CREW_ID,
            message="hello",
        )
        self.assertTrue(_is_error(result), f"Expected error steering nonexistent task: {result}")


# ── 4. Response schemas ───────────────────────────────────────────────────────


@unittest.skipUnless(GHOSTSHIP_E2E_URL, _SKIP_REASON)
class TestResponseSchemas(unittest.TestCase):
    """Verify all expected fields are present on tool responses.

    Uses setUpClass/tearDownClass so the crew is launched once for all
    five schema tests rather than once per test (~4 min saving).
    """

    CREW_ID = "e2e-schema"
    _CREW_FIELDS = {
        "crew_id", "container", "status", "composition",
        "created_at", "gateway_healthy", "crew_image_version",
        "agents", "policy_version",
    }

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

    def test_launch_response_shape(self):
        # Already launched in setUp — launch a second named crew for a clean shape check
        crew_id = "e2e-schema-shape"
        try:
            _mcp_call("nuke", crew_id=crew_id, confirm=True)
        except Exception:
            pass
        result = _mcp_call("launch", crew_id=crew_id)
        try:
            self.assertEqual(result.get("crew_id"), crew_id)
            self.assertEqual(result.get("status"), "ready")
            self.assertIn("container", result)
            self.assertIn("gateway_url", result)
        finally:
            _mcp_call("nuke", crew_id=crew_id, confirm=True)

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


if __name__ == "__main__":
    unittest.main()
