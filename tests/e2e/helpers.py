"""Shared helpers for the Ghost Academy e2e test suite."""

import json
import os
import time

import httpx

GHOSTSHIP_E2E_URL = os.environ.get("GHOSTSHIP_E2E_URL", "").rstrip("/")
GHOSTSHIP_API_KEY = os.environ.get("GHOSTSHIP_API_KEY", "")
GHOSTSHIP_E2E_KIRO_AUTH = os.environ.get("GHOSTSHIP_E2E_KIRO_AUTH", "") not in ("", "0", "false")

# Podman socket used by the transport — needed for tests that must stop a
# container directly (no transport MCP tool exposes a stop-without-nuke path).
# Override via GHOSTSHIP_PODMAN_SOCKET when pointing at a remote or
# non-default socket path.
GHOSTSHIP_PODMAN_SOCKET = os.environ.get(
    "GHOSTSHIP_PODMAN_SOCKET",
    "/run/user/1000/ghost-academy/podman.sock",
)

_SKIP_REASON = "GHOSTSHIP_E2E_URL not set"


def mcp_call(tool: str, *, api_key: str = GHOSTSHIP_API_KEY, **kwargs) -> dict:
    """POST a JSON-RPC tool call to /mcp, parse the SSE envelope, return result dict.

    The transport uses Streamable HTTP (MCP spec): a plain POST returns an SSE
    response with a single ``event: message`` frame containing the JSON-RPC
    response. This helper peels off the SSE envelope and returns the parsed
    result dict, or ``{"error": <text>}`` when ``isError: true``.
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

    # Parse SSE envelope: find the "data: {...}" line
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
        # Surface non-JSON error text clearly
        return {"error": text}


def is_error(result: dict) -> bool:
    """Return True if the result contains a transport-level error."""
    return "error" in result


# ── Podman helpers ────────────────────────────────────────────────────────────
# These talk directly to the Podman socket used by the transport.  They are
# needed for tests that must manipulate container state in ways that have no
# MCP tool equivalent (e.g. stopping a container without nuking it).
# They require GHOSTSHIP_PODMAN_SOCKET to be reachable from the test runner.


def _podman_client(socket: str = GHOSTSHIP_PODMAN_SOCKET) -> httpx.Client:
    """Return an httpx.Client configured to talk to a Podman Unix socket."""
    transport = httpx.HTTPTransport(uds=socket)
    return httpx.Client(transport=transport, base_url="http://localhost")


def container_stop(container: str, timeout: int = 10) -> None:
    """Stop a container via the Podman REST API (POST /libpod/containers/{name}/stop).

    ``timeout`` is the seconds Podman waits for a graceful SIGTERM before
    sending SIGKILL.  Raises on unexpected HTTP errors; treats 204 (stopped),
    304 (already stopped), and 404 (container gone) as success.
    """
    with _podman_client() as client:
        resp = client.post(
            f"/libpod/containers/{container}/stop",
            params={"t": timeout},
            timeout=30.0,
        )
        # 204 = stopped, 304 = already stopped, 404 = container gone — all fine
        if resp.status_code not in (204, 304, 404):
            resp.raise_for_status()


def container_is_running(container: str) -> bool:
    """Return True if the named container's Podman state is 'running'.

    Returns False for both stopped and non-existent containers.
    """
    with _podman_client() as client:
        resp = client.get(f"/libpod/containers/{container}/json", timeout=10.0)
        if resp.status_code != 200:
            return False
        return resp.json().get("State", {}).get("Status") == "running"


def wait_until_stopped(container: str, timeout: int = 30) -> bool:
    """Poll until the container is no longer running or ``timeout`` elapses.

    Returns True if the container stopped within the timeout, False otherwise.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not container_is_running(container):
            return True
        time.sleep(1)
    return False
