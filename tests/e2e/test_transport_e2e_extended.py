"""Extended e2e tests — error paths, schedule/steer tools, response schemas.

Extends the smoke suite from TRN-79. Same skip guard: set GHOSTSHIP_E2E_URL
to a live transport to run, unset to skip cleanly.

    GHOSTSHIP_E2E_URL=http://academy.penguin-piano.ts.net bash tests/run.sh --e2e
"""

import json
import os
import time
import unittest

import httpx

# ── Config ────────────────────────────────────────────────────────────────────

GHOSTSHIP_E2E_URL = os.environ.get("GHOSTSHIP_E2E_URL", "").rstrip("/")
GHOSTSHIP_API_KEY = os.environ.get("GHOSTSHIP_API_KEY", "")

_SKIP_REASON = "GHOSTSHIP_E2E_URL not set"

# ── Helpers ───────────────────────────────────────────────────────────────────


def _mcp_call(tool: str, *, api_key: str = "", **kwargs) -> dict:
    """POST a JSON-RPC tool call to /mcp, parse the SSE envelope, return result dict.

    Returns a dict with either the parsed JSON result, or
    ``{"error": <text>}`` when the MCP result has ``isError: true`` or the
    text content is not valid JSON (e.g. a plain-text error message).
    """
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": tool, "arguments": kwargs},
        "id": 1,
    }

    resp = httpx.post(
        f"{GHOSTSHIP_E2E_URL}/mcp",
        json=payload,
        headers=headers,
        timeout=60.0,
    )
    resp.raise_for_status()

    data_line = None
    for line in resp.text.splitlines():
        if line.startswith("data:"):
            data_line = line[len("data:"):].strip()
            break

    if data_line is None:
        raise ValueError(f"No data line in SSE response: {resp.text!r}")

    rpc = json.loads(data_line)
    if "error" in rpc:
        raise RuntimeError(f"MCP error: {rpc['error']}")

    mcp_result = rpc["result"]
    content = mcp_result.get("content", [])
    text = content[0]["text"] if content else ""

    # isError=true means the transport returned a plain-text error message
    if mcp_result.get("isError"):
        return {"error": text}

    if not text:
        return {}

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Shouldn't happen for non-error responses, but surface it clearly
        return {"error": text}


def _is_error(result: dict) -> bool:
    """Return True if the result contains a transport-level error key."""
    return "error" in result


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
        result = _mcp_call("launch", crew_id=self.CREW_ID)
        self.assertEqual(result.get("status"), "ready")

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
        result = _mcp_call("launch", crew_id=self.CREW_ID)
        self.assertEqual(result.get("status"), "ready")

    def tearDown(self):
        try:
            _mcp_call("nuke", crew_id=self.CREW_ID, confirm=True)
        except Exception:
            pass

    def test_steer_running_task_returns_ok(self):
        # Dispatch a slow task
        dispatch = _mcp_call(
            "dispatch",
            crew_id=self.CREW_ID,
            agent="ghost",
            task="Count slowly from 1 to 100, pausing between each number.",
        )
        task_id = dispatch.get("task_id")
        self.assertIsNotNone(task_id)

        # Give it a moment to start
        time.sleep(3)

        # Steer it — we only verify the transport accepted the call, not the agent outcome
        steer_result = _mcp_call(
            "steer",
            task_id=task_id,
            crew_id=self.CREW_ID,
            message="Stop counting. Just say DONE.",
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
    """Verify all expected fields are present on tool responses."""

    CREW_ID = "e2e-schema"
    _CREW_FIELDS = {
        "crew_id", "container", "status", "composition",
        "created_at", "gateway_healthy", "crew_image_version",
        "agents", "policy_version",
    }

    def setUp(self):
        try:
            _mcp_call("nuke", crew_id=self.CREW_ID, confirm=True)
        except Exception:
            pass
        result = _mcp_call("launch", crew_id=self.CREW_ID)
        self.assertEqual(result.get("status"), "ready")

    def tearDown(self):
        try:
            _mcp_call("nuke", crew_id=self.CREW_ID, confirm=True)
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
