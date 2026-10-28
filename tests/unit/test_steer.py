"""steer() handles gateway refusals instead of raising.

A running-task steer that the crew gateway refused used to escape the tool as
an unhandled ``HTTPStatusError``, so MCP callers only saw "Error executing tool
steer". Now:

- a ``steer_unsupported`` refusal (claude and codex can't interrupt mid-turn)
  is retried as ``mode='follow_up'`` and reported as ``follow_up_queued``;
- any other refusal returns a structured error with the gateway's status and
  body, on the interrupt, force and continue paths alike.
"""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import patch

import httpx

# transport.tools imports transport.files, which needs real starlette routing
# that the unit-test stubs (conftest) don't provide. steer never signs file
# URLs, so a stand-in exposing the two imported names is enough.
if "transport.files" not in sys.modules:
    try:
        import transport.files  # noqa: F401
    except ImportError:
        _files_stub = types.ModuleType("transport.files")
        _files_stub._sign_file_url = lambda *a, **k: ""
        _files_stub._sign_upload_url = lambda *a, **k: ""
        sys.modules["transport.files"] = _files_stub

import transport.tools as tools

_COOKIE = "eyJzZWNyZXQtY29va2llIn0.sig"


def _status_error(status: int, body: str) -> httpx.HTTPStatusError:
    response = SimpleNamespace(status_code=status, text=body)
    return httpx.HTTPStatusError(f"HTTP {status}", request=None, response=response)


def _run_steer(api_side_effect, **steer_kw):
    crew = {"cookie": _COOKIE}
    with patch.object(tools, "_require_crew", return_value=crew), \
            patch.object(tools, "_ensure_crew_running", return_value=crew), \
            patch.object(tools, "_crew_api_with_recovery", side_effect=api_side_effect):
        return tools.steer(task_id="t1", message="stop", crew_id="c1", **steer_kw)


_UNSUPPORTED = (
    '{"error": "steer_unsupported: this run\'s backend cannot guarantee a '
    'mid-turn steer - use mode=\'follow_up\'", "code": "steer_failed"}'
)


def test_running_steer_gateway_error_returns_structured_error():
    def api(crew, crew_id, method, path, **kw):
        if method == "GET":
            return {"done": False}
        raise _status_error(503, f"session_starting cookie={_COOKIE}")

    result = _run_steer(api)

    assert "HTTP 503" in result["error"]
    assert "session_starting" in result["error"]
    assert _COOKIE not in result["error"]
    assert "force=True" in result["hint"]


def test_steer_unsupported_falls_back_to_follow_up():
    sent = []

    def api(crew, crew_id, method, path, **kw):
        if method == "GET":
            return {"done": False}
        sent.append(kw["json"])
        if "mode" not in kw["json"]:
            raise _status_error(502, _UNSUPPORTED)
        return {"id": "t1", "status": "follow_up_queued"}

    result = _run_steer(api)

    assert sent == [{"message": "stop"}, {"message": "stop", "mode": "follow_up"}]
    assert result["action"] == "follow_up_queued"
    assert result["task_id"] == "t1"


def test_follow_up_refusal_returns_structured_error():
    def api(crew, crew_id, method, path, **kw):
        if method == "GET":
            return {"done": False}
        if "mode" not in kw["json"]:
            raise _status_error(502, _UNSUPPORTED)
        raise _status_error(409, '{"error": "not_running", "code": "not_running"}')

    result = _run_steer(api)

    assert "follow-up" in result["error"]
    assert "HTTP 409" in result["error"]


def test_continue_on_finished_task_gateway_error_returns_structured_error():
    def api(crew, crew_id, method, path, **kw):
        if method == "GET":
            return {"done": True}
        raise _status_error(404, '{"error": "gone", "code": "conversation_gone"}')

    result = _run_steer(api)

    assert "continue for finished task t1" in result["error"]
    assert "HTTP 404" in result["error"]


def test_force_steer_gateway_error_returns_structured_error():
    def api(crew, crew_id, method, path, **kw):
        if method == "GET":
            return {"done": False}
        if method == "DELETE":
            return {}
        raise _status_error(409, '{"error": "busy", "code": "conversation_busy"}')

    result = _run_steer(api, force=True)

    assert "force steer for task t1" in result["error"]
    assert "HTTP 409" in result["error"]


def test_running_steer_success_unchanged():
    def api(crew, crew_id, method, path, **kw):
        return {"done": False} if method == "GET" else {}

    result = _run_steer(api)

    assert result == {"task_id": "t1", "crew_id": "c1", "action": "steered", "message": "stop"}
