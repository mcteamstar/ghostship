"""TRN-220 — crew-gateway REST entry point header invariant.

Asserts the transport host authenticates to a crew gateway on the external
dashboard-cookie path only (``Cookie`` + ``Origin``) and never emits the
internal-API headers ``X-Internal-Secret`` / ``X-Session-Key``.

KiroCrew 0.9.0 (PR #2424 / issue #302) adds unix-socket peer-credential
validation to the internal-API path: a caller whose OS UID differs from the
gateway's ``kirocrew`` process is rejected even with a valid shared secret.
The transport host runs under a different UID, so an internal-secret call from
here would be rejected on the peer-cred check. This test turns a future change
that added such a header on the transport path into a loud CI failure, and
asserts the guard in ``_crew_api`` refuses the forbidden headers if a caller
ever passes them via ``headers=``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.unit._stubs import install_import_stubs

install_import_stubs()

import transport.lifecycle as _lifecycle  # noqa: E402 (after stub install)


def _run_crew_api(**extra_kw):
    """Call ``_crew_api`` with ``_http`` patched; return what it emitted."""
    crew = {"container": "crew-x", "cookie": "abc"}
    captured: dict = {}

    fake_resp = MagicMock()
    fake_resp.json.return_value = {}
    fake_resp.raise_for_status.return_value = None

    def _req(method, url, headers=None, **kw):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = headers or {}
        return fake_resp

    with patch.object(_lifecycle, "_http") as http:
        http.request.side_effect = _req
        _lifecycle._crew_api(crew, "GET", "/api/spawn", **extra_kw)

    return captured


def test_crew_api_sends_cookie_path_only():
    captured = _run_crew_api()
    headers = captured["headers"]

    assert "Cookie" in headers
    assert headers["Cookie"].startswith("mc_token_")
    assert "Origin" in headers

    # The whole point of TRN-220: no internal-secret headers on this path.
    assert "X-Internal-Secret" not in headers
    assert "X-Session-Key" not in headers

    # Method and path pass through unchanged.
    assert captured["method"] == "GET"
    assert captured["url"].endswith("/api/spawn")


def test_crew_api_only_cookie_and_origin_are_sent():
    # With no caller headers, exactly Cookie + Origin and nothing else.
    headers = _run_crew_api()["headers"]
    assert set(headers) == {"Cookie", "Origin"}


def test_crew_api_rejects_forbidden_internal_headers():
    for forbidden in _lifecycle._FORBIDDEN_INTERNAL_HEADERS:
        with pytest.raises(ValueError) as exc:
            _run_crew_api(headers={forbidden: "whatever"})
        # Refusal names the invariant so the author sees why it is forbidden.
        assert "TRN-220" in str(exc.value)
        assert forbidden in str(exc.value)


def test_crew_api_merges_benign_caller_headers():
    headers = _run_crew_api(headers={"X-Custom": "ok"})["headers"]
    assert headers["X-Custom"] == "ok"
    assert "Cookie" in headers and "Origin" in headers
    assert "X-Internal-Secret" not in headers
    assert "X-Session-Key" not in headers
