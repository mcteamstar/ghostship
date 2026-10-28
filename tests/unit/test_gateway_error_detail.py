"""Gateway error detail reaches the caller when recovery gives up.

Covers the crew-lifecycle requirement "Gateway error detail reaches the
caller": the final CrewUnresponsiveError carries the HTTP status and the
gateway's (redacted, truncated) body, and a 4xx swaps the "check crew status"
suggestion for one that points at the gateway's response. Recovery itself is
unchanged.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

import transport.lifecycle as lc

_COOKIE = "eyJsZWNyZXQtY29va2llIn0.sig"


def _status_error(status: int, body: str) -> httpx.HTTPStatusError:
    # A minimal response object: the unit-test httpx stub has no Request type,
    # and the code under test only reads status_code and text.
    response = SimpleNamespace(status_code=status, text=body)
    return httpx.HTTPStatusError(f"HTTP {status}", request=None, response=response)


def _crew() -> dict:
    return {"container": "gs-x", "cookie": _COOKIE, "status": "running"}


def _run_with_gateway(status: int, body: str):
    """Drive _crew_api_with_recovery against a gateway that always errors."""
    crew = _crew()
    calls = {"api": 0}

    def _always_fail(*_a, **_kw):
        calls["api"] += 1
        raise _status_error(status, body)

    with (
        patch.object(lc, "_crew_api", side_effect=_always_fail),
        patch.object(lc, "_refresh_cookie", return_value=True),
        patch.object(lc, "_ensure_crew_running", side_effect=lambda c, _id: c),
    ):
        with pytest.raises(lc.CrewUnresponsiveError) as excinfo:
            lc._crew_api_with_recovery(crew, "x", "POST", "/api/spawn", json={"agent": "ghost"})
    return str(excinfo.value), calls["api"]


def test_unknown_persona_reason_reaches_caller() -> None:
    message, _ = _run_with_gateway(400, '{"error": "Agent \'ghost\' not found; refusing spawn."}')
    assert "unresponsive" in message
    assert "HTTP 400" in message
    assert "Agent 'ghost' not found" in message
    assert "The crew gateway rejected the request" in message
    assert "check crew status" not in message


def test_body_is_redacted_and_truncated() -> None:
    body = f"cookie={_COOKIE} mc_token_5476=othertoken " + ("x" * 2000)
    message, _ = _run_with_gateway(403, body)
    assert _COOKIE not in message
    assert "othertoken" not in message
    detail = message.split("Last gateway response: HTTP 403: ", 1)[1]
    gateway_body = detail.split(" The crew gateway rejected", 1)[0]
    assert len(gateway_body) <= lc._GATEWAY_DETAIL_LIMIT


def test_recovery_attempts_unchanged() -> None:
    """First call, retry after cookie refresh, retry after restart: three calls."""
    _, api_calls = _run_with_gateway(400, "bad request")
    assert api_calls == 3


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
    message, _ = _run_with_gateway(400, body)
    assert "supersecrettoken123" not in message
    assert "Bearer [redacted]" in message


def test_gs_session_is_redacted() -> None:
    """gs_session=<value> in the gateway body is redacted."""
    body = "gs_session=mysessionvalue123; other cookie data"
    message, _ = _run_with_gateway(400, body)
    assert "mysessionvalue123" not in message
    assert "gs_session=[redacted]" in message


def test_gs_csrf_is_redacted() -> None:
    """gs_csrf=<value> in the gateway body is redacted."""
    body = "gs_csrf=mycsrftoken456; path=/"
    message, _ = _run_with_gateway(400, body)
    assert "mycsrftoken456" not in message
    assert "gs_csrf=[redacted]" in message
