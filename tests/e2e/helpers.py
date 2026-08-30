"""Shared helpers for the Ghost Academy e2e test suite."""

import json
import os

import httpx

GHOSTSHIP_E2E_URL = os.environ.get("GHOSTSHIP_E2E_URL", "").rstrip("/")
GHOSTSHIP_API_KEY = os.environ.get("GHOSTSHIP_API_KEY", "")

_SKIP_REASON = "GHOSTSHIP_E2E_URL not set"


def mcp_call(tool: str, *, api_key: str = "", **kwargs) -> dict:
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
