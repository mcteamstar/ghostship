"""End-to-end tests for the Ghost Academy transport.

Requires a live transport and GHOSTSHIP_E2E_URL env var:

    GHOSTSHIP_E2E_URL=http://academy.penguin-piano.ts.net bash tests/run.sh --e2e

All test classes skip cleanly when GHOSTSHIP_E2E_URL is unset — safe for CI
runs that don't have a transport provisioned.

Optional:
    GHOSTSHIP_API_KEY — if set, the auth gate test also runs.
"""

import json
import os
import time
import unittest

import httpx

# ── Config ────────────────────────────────────────────────────────────────────

GHOSTSHIP_E2E_URL = os.environ.get("GHOSTSHIP_E2E_URL", "").rstrip("/")
GHOSTSHIP_API_KEY = os.environ.get("GHOSTSHIP_API_KEY", "")

_SKIP = not GHOSTSHIP_E2E_URL
_SKIP_REASON = "GHOSTSHIP_E2E_URL not set"

# ── Helpers ───────────────────────────────────────────────────────────────────


def _mcp_call(tool: str, *, api_key: str = "", **kwargs) -> dict:
    """POST a JSON-RPC tool call to /mcp and return the parsed result dict.

    The transport uses Streamable HTTP (MCP spec): a plain POST returns an SSE
    response with a single ``event: message`` frame containing the JSON-RPC
    response.  This helper peels off the SSE envelope and returns the
    ``result`` field (or raises on error).
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

    # Parse SSE envelope: lines like "event: message" and "data: {...}"
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

    # result.content is a list of {text, type} blocks — unwrap the first text
    content = rpc["result"]["content"]
    text = content[0]["text"] if content else "{}"
    return json.loads(text)


# ── 2. Health check ───────────────────────────────────────────────────────────


@unittest.skipUnless(not _SKIP, _SKIP_REASON)
class TestHealthCheck(unittest.TestCase):
    def test_health(self):
        resp = httpx.get(f"{GHOSTSHIP_E2E_URL}/health", timeout=10.0)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.text.strip(), "ok")

    def test_version(self):
        resp = httpx.get(f"{GHOSTSHIP_E2E_URL}/version", timeout=10.0)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("transport", data)
        # semver-ish: non-empty string with at least one dot
        version = data["transport"]
        self.assertIsInstance(version, str)
        self.assertIn(".", version, f"Expected semver in version: {version!r}")


# ── 3. Crew lifecycle ─────────────────────────────────────────────────────────


@unittest.skipUnless(not _SKIP, _SKIP_REASON)
class TestCrewLifecycle(unittest.TestCase):
    CREW_ID = "e2e-lifecycle"

    def setUp(self):
        # Nuke any stale crew from a previous failed test
        try:
            _mcp_call("nuke", crew_id=self.CREW_ID, confirm=True)
        except Exception:
            pass  # fine if it didn't exist

    def tearDown(self):
        try:
            _mcp_call("nuke", crew_id=self.CREW_ID, confirm=True)
        except Exception:
            pass

    def test_launch_and_nuke(self):
        # Launch
        result = _mcp_call("launch", crew_id=self.CREW_ID)
        self.assertEqual(result.get("crew_id"), self.CREW_ID)
        self.assertEqual(result.get("status"), "ready")

        # Verify it appears in crews()
        crews = _mcp_call("crews")
        crew_ids = [c["crew_id"] for c in crews.get("crews", [])]
        self.assertIn(self.CREW_ID, crew_ids)

        # Nuke
        nuke_result = _mcp_call("nuke", crew_id=self.CREW_ID, confirm=True)
        self.assertEqual(nuke_result.get("status"), "nuked")

        # Verify it's gone
        crews_after = _mcp_call("crews")
        crew_ids_after = [c["crew_id"] for c in crews_after.get("crews", [])]
        self.assertNotIn(self.CREW_ID, crew_ids_after)


# ── 4. Dispatch + pickup ──────────────────────────────────────────────────────


@unittest.skipUnless(not _SKIP, _SKIP_REASON)
class TestDispatchPickup(unittest.TestCase):
    CREW_ID = "e2e-dispatch"

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

    def test_dispatch_and_pickup(self):
        # Dispatch a trivial task
        dispatch = _mcp_call(
            "dispatch",
            crew_id=self.CREW_ID,
            agent="ghost",
            task="Print the word DONE and nothing else.",
        )
        task_id = dispatch.get("task_id")
        self.assertIsNotNone(task_id)

        # Poll until done (5s interval, 120s max)
        deadline = time.time() + 120
        result = None
        while time.time() < deadline:
            status = _mcp_call("pickup", crew_id=self.CREW_ID, task_id=task_id)
            if status.get("done"):
                result = status
                break
            time.sleep(5)

        self.assertIsNotNone(result, "Task did not complete within 120s")
        self.assertTrue(result.get("done"))
        self.assertFalse(result.get("error"), f"Task errored: {result.get('error')}")
        self.assertTrue(result.get("result", ""), "Expected non-empty result")


# ── 5. Supply + evac round-trip ───────────────────────────────────────────────


@unittest.skipUnless(not _SKIP, _SKIP_REASON)
class TestSupplyEvac(unittest.TestCase):
    CREW_ID = "e2e-files"
    TEST_PAYLOAD = b"hello e2e ghostship"
    TEST_PATH = "repo/e2e-test.txt"

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

    def test_supply_and_evac(self):
        # Get presigned upload URL
        supply = _mcp_call("supply", crew_id=self.CREW_ID, path=self.TEST_PATH)
        upload_url = supply.get("delivery_url")
        self.assertIsNotNone(upload_url, f"No delivery_url in supply response: {supply}")

        # Upload payload
        up = httpx.post(upload_url, content=self.TEST_PAYLOAD, timeout=30.0)
        self.assertIn(up.status_code, (200, 201), f"Upload failed: {up.status_code} {up.text}")

        # Get presigned download URL
        evac = _mcp_call("evac", crew_id=self.CREW_ID, path=self.TEST_PATH)
        download_url = evac.get("download_url") or evac.get("url")
        self.assertIsNotNone(download_url, f"No download_url in evac response: {evac}")

        # Download and verify
        down = httpx.get(download_url, timeout=30.0)
        self.assertEqual(down.status_code, 200)
        self.assertEqual(down.content, self.TEST_PAYLOAD)


# ── 6. Auth gate ──────────────────────────────────────────────────────────────


@unittest.skipUnless(
    not _SKIP and bool(GHOSTSHIP_API_KEY),
    "GHOSTSHIP_E2E_URL and GHOSTSHIP_API_KEY both required",
)
class TestAuthGate(unittest.TestCase):
    def test_unauthenticated_request_rejected(self):
        resp = httpx.post(
            f"{GHOSTSHIP_E2E_URL}/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "crews", "arguments": {}},
                "id": 1,
            },
            headers={"Content-Type": "application/json"},
            timeout=10.0,
        )
        self.assertEqual(resp.status_code, 401)

    def test_authenticated_request_accepted(self):
        resp = httpx.post(
            f"{GHOSTSHIP_E2E_URL}/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "crews", "arguments": {}},
                "id": 1,
            },
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {GHOSTSHIP_API_KEY}",
            },
            timeout=10.0,
        )
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
