"""Gateway error detail reaches the caller when recovery gives up.

Covers the crew-lifecycle requirement "Gateway error detail reaches the
caller": the final CrewUnresponsiveError carries the HTTP status and the
gateway's (redacted, truncated) body, and a 4xx swaps the "check crew status"
suggestion for one that points at the gateway's response. Recovery itself is
unchanged.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx2 as httpx
import pytest

import transport.lifecycle as lc

_COOKIE = "eyJsZWNyZXQtY29va2llIn0.sig"


def _status_error(status: int, body: str) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "http://gateway.test/api/spawn/task")
    response = httpx.Response(status, request=request, text=body)
    return httpx.HTTPStatusError(f"HTTP {status}", request=request, response=response)


def _crew() -> dict:
    return {"container": "gs-x", "cookie": _COOKIE, "status": "running"}


def _format_gateway_failure(status: int, body: str) -> str:
    return str(lc._unresponsive_error("x", "gateway request failed", _crew(), _status_error(status, body)))


def test_unknown_persona_reason_reaches_caller() -> None:
    message = _format_gateway_failure(400, '{"error": "Agent \'ghost\' not found; refusing spawn."}')
    assert "unresponsive" in message
    assert "HTTP 400" in message
    assert "Agent 'ghost' not found" in message
    assert "The crew gateway rejected the request" in message
    assert "check crew status" not in message


def test_body_is_redacted_and_truncated() -> None:
    body = f"cookie={_COOKIE} mc_token_5476=othertoken " + ("x" * 2000)
    message = _format_gateway_failure(403, body)
    assert _COOKIE not in message
    assert "othertoken" not in message
    detail = message.split("Last gateway response: HTTP 403: ", 1)[1]
    gateway_body = detail.split(" The crew gateway rejected", 1)[0]
    assert len(gateway_body) <= lc._GATEWAY_DETAIL_LIMIT


def test_server_error_keeps_crew_status_suggestion() -> None:
    err = _status_error(502, "bad gateway")
    message = str(lc._unresponsive_error("x", "it failed", _crew(), err))
    assert "HTTP 502: bad gateway" in message
    assert "check crew status with crews()" in message


def test_no_http_error_keeps_original_message() -> None:
    message = str(lc._unresponsive_error("x", "it failed", _crew(), ConnectionError("reset")))
    assert message == (
        "crew x is unresponsive — it failed. "
        "Suggestion: check crew status with crews() or try again in a moment."
    )


def test_bearer_token_is_redacted() -> None:
    """Authorization: Bearer <token> in the gateway body is redacted."""
    body = "Authorization: Bearer supersecrettoken123 some other text"
    message = _format_gateway_failure(400, body)
    assert "supersecrettoken123" not in message
    assert "Bearer [redacted]" in message


def test_gs_session_is_redacted() -> None:
    """gs_session=<value> in the gateway body is redacted."""
    body = "gs_session=mysessionvalue123; other cookie data"
    message = _format_gateway_failure(400, body)
    assert "mysessionvalue123" not in message
    assert "gs_session=[redacted]" in message


def test_gs_csrf_is_redacted() -> None:
    """gs_csrf=<value> in the gateway body is redacted."""
    body = "gs_csrf=mycsrftoken456; path=/"
    message = _format_gateway_failure(400, body)
    assert "mycsrftoken456" not in message
    assert "gs_csrf=[redacted]" in message


@pytest.mark.parametrize("backend", [None, "kiro", "claude", "codex"])
def test_transport_spawn_names_backend_even_on_refusal(backend):
    crew = _crew()
    if backend is not None:
        crew["acp_backend"] = backend
    body = {"task": "hello", "parent_session": "dashboard:member-raven"}
    refusal = _status_error(422, "Backend unavailable")
    with patch.object(lc._gateway_client, "request", side_effect=refusal) as gateway:
        with pytest.raises(httpx.HTTPStatusError) as raised:
            lc._crew_api_with_recovery(crew, "x", "POST", "/api/spawn", json=body)

    assert raised.value is refusal
    gateway.assert_called_once_with(
        crew, "POST", "/api/spawn", json={**body, "backend": backend or "kiro"}
    )
    assert "backend" not in body
