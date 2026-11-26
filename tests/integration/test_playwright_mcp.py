"""Launch the shipped Playwright MCP and Chromium from the crew image."""

from __future__ import annotations

import json
import os
import selectors
import subprocess
import tempfile
import time


COMMAND = [
    "npx",
    "--yes",
    "@playwright/mcp@latest",
    "--executable-path",
    "/usr/bin/chromium",
    "--headless",
    "--no-sandbox",
]


def _stderr_text(stream) -> str:
    stream.seek(0)
    return stream.read().decode(errors="replace")


def _receive(
    proc: subprocess.Popen, request_id: int, stderr, timeout: float = 120
) -> dict:
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    buffer = b""
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            events = selector.select(max(0, deadline - time.monotonic()))
            if not events:
                break
            chunk = os.read(proc.stdout.fileno(), 4096)
            if not chunk:
                raise RuntimeError(
                    "Playwright MCP exited before replying: " + _stderr_text(stderr)
                )
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                try:
                    message = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if message.get("id") == request_id:
                    if "error" in message:
                        raise RuntimeError(f"MCP error: {message['error']}")
                    return message
        raise TimeoutError(
            f"Timed out waiting for MCP request {request_id}; stderr: {_stderr_text(stderr)}"
        )
    finally:
        selector.close()


def _send(proc: subprocess.Popen, message: dict) -> None:
    proc.stdin.write((json.dumps(message) + "\n").encode())
    proc.stdin.flush()


def main() -> None:
    env = os.environ.copy()
    env["PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"] = "1"

    # An empty browser cache proves the configured executable path, rather than a
    # first-use Playwright browser download, supplies Chromium.
    with tempfile.TemporaryDirectory(prefix="empty-playwright-browsers-") as browser_cache:
        env["PLAYWRIGHT_BROWSERS_PATH"] = browser_cache
        with tempfile.TemporaryFile() as stderr:
            proc = subprocess.Popen(
                COMMAND,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr,
                env=env,
            )
            try:
                _send(proc, {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "ghostship-image-smoke", "version": "1"},
                    },
                })
                _receive(proc, 1, stderr)
                _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
                _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
                tools = _receive(proc, 2, stderr)["result"]["tools"]
                tool_names = {tool["name"] for tool in tools}
                required = {"browser_navigate", "browser_snapshot"}
                missing = required - tool_names
                if missing:
                    raise AssertionError(
                        f"Playwright MCP is missing tools: {sorted(missing)}"
                    )

                _send(proc, {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "browser_navigate",
                        "arguments": {
                            "url": "data:text/html,<title>TRN-369-smoke</title><h1>local-page-ok</h1>"
                        },
                    },
                })
                navigation = _receive(proc, 3, stderr)["result"]
                if navigation.get("isError"):
                    raise RuntimeError(f"Browser navigation failed: {navigation['content']}")
                navigation_text = "\n".join(
                    item.get("text", "")
                    for item in navigation.get("content", [])
                    if item.get("type") == "text"
                )
                if "TRN-369-smoke" not in navigation_text:
                    raise AssertionError(f"Unexpected navigation result: {navigation_text}")

                _send(proc, {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "browser_snapshot", "arguments": {}},
                })
                snapshot = _receive(proc, 4, stderr)["result"]
                if snapshot.get("isError"):
                    raise RuntimeError(f"Browser snapshot failed: {snapshot['content']}")
                snapshot_text = "\n".join(
                    item.get("text", "")
                    for item in snapshot.get("content", [])
                    if item.get("type") == "text"
                )
                if (
                    "TRN-369-smoke" not in snapshot_text
                    or "local-page-ok" not in snapshot_text
                ):
                    raise AssertionError(f"Unexpected page snapshot: {snapshot_text}")

                print("Playwright MCP opened a local page with /usr/bin/chromium.")
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
                if proc.stdin:
                    proc.stdin.close()
                if proc.stdout:
                    proc.stdout.close()


if __name__ == "__main__":
    main()
