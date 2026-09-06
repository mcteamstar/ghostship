"""Auth middleware tests split from test_server.py (trn-119).

Covers BearerAuthMiddleware, TRN-38 security hardening, and proxy query
sanitisation. Mock paths point at transport.auth / transport.server per TRN-116.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import hmac
import importlib as _importlib
import inspect
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from unittest.mock import ANY, Mock, MagicMock, patch

import httpx
import transport.registry as _registry_mod  # noqa: F401

from tests.unit.helpers import Request, server, lifecycle, monitors, academy  # noqa: F401


class _FakeDownstream:
    """Minimal ASGI app that records whether it was called."""

    def __init__(self) -> None:
        self.called = False
        self.scope = None

    async def __call__(self, scope, receive, send) -> None:
        self.called = True
        self.scope = scope
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"OK"})
def _http_scope(headers: list[tuple[bytes, bytes]] | None = None) -> dict:
    return {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "headers": headers or [],
    }
def _run_asgi(app, scope, body: bytes = b"") -> tuple[int, list, bytes]:
    """Run an ASGI app synchronously and return (status, headers, body)."""
    status = None
    resp_headers = []
    resp_body = b""

    async def receive():
        return {"type": "http.request", "body": body}

    async def send(msg):
        nonlocal status, resp_headers, resp_body
        if msg["type"] == "http.response.start":
            status = msg["status"]
            resp_headers = msg.get("headers", [])
        elif msg["type"] == "http.response.body":
            resp_body += msg.get("body", b"")

    asyncio.run(app(scope, receive, send))
    return status, resp_headers, resp_body
class _FakeStreamRequest:
    """Minimal async-compatible request stub for proxy handler tests."""

    def __init__(
        self,
        method: str = "GET",
        path: str = "/crews/demo/ui",
        headers: dict[str, str] | None = None,
        body: bytes = b"",
        query_string: bytes = b"",
    ) -> None:
        self.method = method
        self.scope = {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": query_string,
        }
        self.headers = headers or {}
        self._body = body

    async def body(self) -> bytes:
        return self._body
class _FakeUpstreamResponse:
    """httpx.Response-like stub returned by _async_http.stream() context manager."""

    def __init__(
        self,
        status_code: int = 200,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = dict(headers or {})

    async def aread(self) -> bytes:
        return self.content

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass
class BearerAuthMiddlewareTests(unittest.TestCase):
    """Tests for the BearerAuthMiddleware pure ASGI wrapper."""

    def test_disabled_mode_passes_all_requests(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="")
        scope = _http_scope()
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 200)
        self.assertTrue(downstream.called)

    def test_valid_bearer_forwards_to_downstream(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="secret-key-123")
        scope = _http_scope([(b"authorization", b"Bearer secret-key-123")])
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 200)
        self.assertTrue(downstream.called)

    def test_valid_bearer_case_insensitive_scheme(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="mykey")
        scope = _http_scope([(b"authorization", b"BEARER mykey")])
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 200)
        self.assertTrue(downstream.called)

    def test_missing_header_returns_401(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="secret")
        scope = _http_scope([])
        status, headers, body = _run_asgi(mw, scope)
        self.assertEqual(status, 401)
        self.assertFalse(downstream.called)
        self.assertIn([b"www-authenticate", b"Bearer"], headers)
        self.assertEqual(body, b"Unauthorized")

    def test_wrong_key_returns_401(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="correct")
        scope = _http_scope([(b"authorization", b"Bearer wrong")])
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 401)
        self.assertFalse(downstream.called)

    def test_malformed_no_bearer_prefix_returns_401(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="secret")
        scope = _http_scope([(b"authorization", b"Basic c2VjcmV0")])
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 401)
        self.assertFalse(downstream.called)

    def test_duplicate_authorization_headers_returns_401(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="secret")
        scope = _http_scope([
            (b"authorization", b"Bearer secret"),
            (b"authorization", b"Bearer secret"),
        ])
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 401)
        self.assertFalse(downstream.called)

    def test_empty_token_after_bearer_returns_401(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="secret")
        scope = _http_scope([(b"authorization", b"Bearer ")])
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 401)
        self.assertFalse(downstream.called)

    def test_non_http_scope_passes_through(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="secret")
        scope = {"type": "lifespan"}
        _run_asgi(mw, scope)
        self.assertTrue(downstream.called)

    def test_constant_time_comparison_used(self) -> None:
        """Verify hmac.compare_digest is used (not == operator)."""
        import inspect
        source = inspect.getsource(server.BearerAuthMiddleware.__call__)
        self.assertIn("hmac.compare_digest", source)
        self.assertNotIn("== self._key", source)

    def test_rejected_requests_never_reach_downstream(self) -> None:
        """Ensure all rejection paths never invoke the downstream app."""
        key = "correct-key"
        bad_cases = [
            [],  # missing
            [(b"authorization", b"Bearer wrong")],  # wrong
            [(b"authorization", b"Token correct-key")],  # bad scheme
            [(b"authorization", b"Bearer correct-key"), (b"authorization", b"Bearer correct-key")],  # dup
            [(b"authorization", b"Bearer ")],  # empty token
        ]
        for headers in bad_cases:
            downstream = _FakeDownstream()
            mw = server.BearerAuthMiddleware(downstream, api_key=key)
            status, _, _ = _run_asgi(mw, _http_scope(headers))
            self.assertEqual(status, 401, f"Expected 401 for headers={headers}")
            self.assertFalse(downstream.called, f"Downstream called for headers={headers}")
class TestTrn38SecurityHardening(unittest.TestCase):
    """Tests for TRN-38 security hardening changes."""

    # ── 9.1 HMAC token length is now 32 hex chars (128-bit) ──────────────────

    def test_sign_file_url_hmac_is_32_hex_chars(self) -> None:
        """_sign_file_url produces a 64-char hex sig (not 32)."""
        url = server._sign_file_url("demo", "repo/file.txt")
        query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        self.assertEqual(len(query["sig"]), 64, f"sig length {len(query['sig'])} != 32: {query['sig']}")

    def test_sign_upload_url_hmac_is_32_hex_chars(self) -> None:
        """_sign_upload_url produces a 64-char hex sig (not 32)."""
        url = server._sign_upload_url("demo", "repo")
        query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        self.assertEqual(len(query["sig"]), 64, f"sig length {len(query['sig'])} != 32: {query['sig']}")

    def test_16_char_sig_rejected_by_verify_file_token(self) -> None:
        """A legacy 16-char sig is rejected by _verify_file_token (length mismatch)."""
        import hmac as _hmac, hashlib as _hashlib
        expires = str(int(time.time()) + 300)
        payload = f"demo:repo/file.txt:::{expires}"
        short_sig = _hmac.new(
            server._FILE_SECRET.encode(), payload.encode(), _hashlib.sha256
        ).hexdigest()[:16]
        self.assertFalse(
            server._verify_file_token("demo", "repo/file.txt", expires, short_sig)
        )

    # ── 9.2 Upload mode signing ───────────────────────────────────────────────

    def test_plain_token_rejected_when_unpack_mode_presented(self) -> None:
        """Token signed with mode='' fails when mode='unpack' is verified."""
        url = server._sign_upload_url("demo", "repo")  # mode=""
        query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        self.assertFalse(
            server._verify_file_token(
                "demo", "repo", query["expires"], query["sig"], mode="unpack"
            ),
            "Plain token should fail verification when mode='unpack' is presented",
        )

    def test_unpack_token_rejected_when_plain_mode_presented(self) -> None:
        """Token signed with mode='unpack' fails when mode='' is verified."""
        url = server._sign_upload_url("demo", "repo", unpack=True)
        query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        self.assertFalse(
            server._verify_file_token(
                "demo", "repo", query["expires"], query["sig"], mode=""
            ),
            "Unpack token should fail verification when mode='' is presented",
        )

    def test_bundle_token_rejected_when_plain_mode_presented(self) -> None:
        """Token signed with mode='bundle' fails when mode='' is verified."""
        url = server._sign_upload_url("demo", "repo", bundle=True)
        query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        self.assertFalse(
            server._verify_file_token(
                "demo", "repo", query["expires"], query["sig"], mode=""
            ),
            "Bundle token should fail verification when mode='' is presented",
        )

    def test_upload_mode_round_trips_correctly(self) -> None:
        """Tokens round-trip: plain/unpack/bundle each verify with matching mode."""
        for unpack, bundle, expected_mode in [
            (False, False, ""),
            (True, False, "unpack"),
            (False, True, "bundle"),
        ]:
            with self.subTest(mode=expected_mode):
                url = server._sign_upload_url("demo", "repo", unpack=unpack, bundle=bundle)
                query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
                self.assertTrue(
                    server._verify_file_token(
                        "demo", "repo", query["expires"], query["sig"], mode=expected_mode
                    ),
                    f"Mode '{expected_mode}' token failed round-trip verification",
                )

    # ── 9.3 _handle_file_put rejects mode mismatch with 403 ──────────────────

    def test_handle_file_put_rejects_bundle_flag_on_plain_token(self) -> None:
        """PUT with bundle=1 query param on a plain-mode token returns 403."""
        # Sign a plain (mode="") token
        url = server._sign_upload_url("crewone", "repo/file.txt")
        query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}

        # Craft request: add bundle=1 to query params (mode mismatch)
        tampered_query = dict(query)
        tampered_query["bundle"] = "1"
        request = Request("crewone", "repo/file.txt", b"data", tampered_query)

        crew = {"container": "gs-crewone"}
        with (
            patch.object(lifecycle, "_require_crew", return_value=crew),
            patch.object(server, "_require_crew", return_value=crew),
            patch.object(lifecycle, "_ensure_crew_running", return_value=crew),
            patch.object(server, "_ensure_crew_running", return_value=crew),
        ):
            response = asyncio.run(server._handle_file_put(request))

        self.assertEqual(response.status_code, 403)

    # ── 9.4 evac empty path returns error ────────────────────────────────────

    def test_evac_empty_path_returns_error(self) -> None:
        """evac(path='') returns {'error': 'path must not be empty'}."""
        crew = {"container": "gs-demo"}
        with (
            patch.object(lifecycle, "_require_crew", return_value=crew),
            patch.object(server, "_require_crew", return_value=crew),
            patch.object(lifecycle, "_ensure_crew_running", return_value=crew),
            patch.object(server, "_ensure_crew_running", return_value=crew),
        ):
            result = server.evac("", crew_id="demo")

        self.assertIn("error", result)
        self.assertIn("empty", result["error"].lower())

    def test_evac_slash_only_path_returns_error(self) -> None:
        """evac(path='/') strips to '' and returns error."""
        crew = {"container": "gs-demo"}
        with (
            patch.object(lifecycle, "_require_crew", return_value=crew),
            patch.object(server, "_require_crew", return_value=crew),
            patch.object(lifecycle, "_ensure_crew_running", return_value=crew),
            patch.object(server, "_ensure_crew_running", return_value=crew),
        ):
            result = server.evac("/", crew_id="demo")

        self.assertIn("error", result)

    # ── 9.5 / 9.6 crew_id format validation in file handlers ─────────────────

    def _make_get_request(self, crew_id: str, path: str) -> "Request":
        """Return a signed GET request for the given crew_id (bypassing real signing)."""
        expires = str(int(time.time()) + 300)
        # Use a patched _verify_file_token — we test the crew_id guard, not the sig
        return Request(crew_id, path, b"", {"expires": expires, "sig": "x" * 32})

    def _make_put_request(self, crew_id: str, path: str) -> "Request":
        return Request(crew_id, path, b"data", {"expires": str(int(time.time()) + 300), "sig": "x" * 32})

    def test_handle_file_get_rejects_crew_id_with_slash(self) -> None:
        """GET returns 400 for crew_id containing '/'."""
        request = self._make_get_request("crew/bad", "file.txt")
        response = asyncio.run(server._handle_file_get(request))
        self.assertEqual(response.status_code, 400)

    def test_handle_file_get_rejects_crew_id_with_dotdot(self) -> None:
        """GET returns 400 for crew_id containing '..'."""
        request = self._make_get_request("crew..bad", "file.txt")
        response = asyncio.run(server._handle_file_get(request))
        self.assertEqual(response.status_code, 400)

    def test_handle_file_get_rejects_crew_id_with_percent(self) -> None:
        """GET returns 400 for crew_id containing '%'."""
        request = self._make_get_request("crew%20bad", "file.txt")
        response = asyncio.run(server._handle_file_get(request))
        self.assertEqual(response.status_code, 400)

    def test_handle_file_get_rejects_crew_id_with_uppercase(self) -> None:
        """GET returns 400 for crew_id containing uppercase letters."""
        request = self._make_get_request("CrewBad", "file.txt")
        response = asyncio.run(server._handle_file_get(request))
        self.assertEqual(response.status_code, 400)

    def test_handle_file_put_rejects_crew_id_with_slash(self) -> None:
        """PUT returns 400 for crew_id containing '/'."""
        request = self._make_put_request("crew/bad", "file.txt")
        response = asyncio.run(server._handle_file_put(request))
        self.assertEqual(response.status_code, 400)

    def test_handle_file_put_rejects_crew_id_with_dotdot(self) -> None:
        """PUT returns 400 for crew_id containing '..'."""
        request = self._make_put_request("crew..bad", "file.txt")
        response = asyncio.run(server._handle_file_put(request))
        self.assertEqual(response.status_code, 400)

    def test_handle_file_put_rejects_crew_id_with_percent(self) -> None:
        """PUT returns 400 for crew_id containing '%'."""
        request = self._make_put_request("crew%20bad", "file.txt")
        response = asyncio.run(server._handle_file_put(request))
        self.assertEqual(response.status_code, 400)

    def test_handle_file_put_rejects_crew_id_with_uppercase(self) -> None:
        """PUT returns 400 for crew_id containing uppercase letters."""
        request = self._make_put_request("CrewBad", "file.txt")
        response = asyncio.run(server._handle_file_put(request))
        self.assertEqual(response.status_code, 400)

    # ── 9.7 _save_registry produces 0o600 mode ───────────────────────────────

    def test_save_registry_produces_0o600_permissions(self) -> None:
        """_save_registry writes crews.json with mode 0o600."""
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "crews.json"
            reg = {"crews": {}}
            with (
                patch.object(server, "DATA_DIR", Path(tmp)),
                patch.object(server, "REGISTRY_PATH", registry_path),
                patch.object(_registry_mod, "DATA_DIR", Path(tmp)),
                patch.object(_registry_mod, "REGISTRY_PATH", registry_path),
            ):
                server._save_registry(reg)

            self.assertTrue(registry_path.exists())
            mode = stat.S_IMODE(os.stat(registry_path).st_mode)
            self.assertEqual(
                mode, 0o600,
                f"Expected 0o600, got 0o{mode:03o}",
            )

    # ── 9.8 _inject_policy output does not contain admiral_secret ────────────

    def test_inject_policy_output_does_not_contain_admiral_secret(self) -> None:
        """_inject_policy does not write admiral_secret into admission_policy.json."""
        captured_scripts: list[str] = []

        def capture_exec(container: str, cmd: list[str]) -> str:
            if cmd[0] == "python3":
                captured_scripts.append(cmd[2])
            return "policy injected version=1"

        mock_podman = Mock()
        mock_podman.container_exec_checked.side_effect = capture_exec

        policy_content = json.dumps({
            "version": "1",
            "commands": {"deny": []},
        })

        with patch("transport.lifecycle.Path") as MockPath:
            composition_path = Mock()
            composition_path.exists.return_value = False
            default_path = Mock()
            default_path.exists.return_value = True
            default_path.read_text.return_value = policy_content

            def path_side(arg):
                if "default.json" in str(arg):
                    return default_path
                return composition_path

            MockPath.side_effect = path_side

            server._inject_policy(mock_podman, "gs-test", "spec-ops", "MY_SECRET_VALUE")

        # Verify none of the exec scripts embed the literal secret
        # trust_keys IS required in admission_policy.json — KiroCrew governance
        # uses it to verify the security policy signature. The threat model
        # (single-operator, isolated containers) accepts this. See docs/auth.md.
        for script in captured_scripts:
            if "admission_body" in script:
                self.assertIn(
                    "'trust_keys'",
                    script,
                    "admission_policy.json must contain trust_keys for KiroCrew governance",
                )
class TestProxyQuerySanitisation(unittest.TestCase):
    """Verify raw query controls are removed by both proxy handlers."""

    CREW = {"container": "gs-demo", "cookie": "test-cookie-val"}

    def _capture_dashboard_url(self, query_string: bytes) -> str:
        captured: list[str] = []
        mock_response = _FakeUpstreamResponse(200, b"ok")

        async def run() -> None:
            with (
                patch.object(server, "_require_crew", return_value=self.CREW),
                patch.object(server, "_ensure_crew_running", return_value=self.CREW),
                patch.object(server, "_async_http") as fake_http,
            ):
                request = _FakeStreamRequest(
                    path="/crews/demo/ui/search",
                    query_string=query_string,
                )

                class StreamCapture:
                    def __call__(self_inner, method, url, **kwargs):
                        captured.append(url)
                        return mock_response

                fake_http.stream = StreamCapture()
                await server._handle_crew_ui_proxy(request)

        asyncio.run(run())
        self.assertEqual(len(captured), 1)
        return captured[0]

    def _capture_api_url(self, query_string: bytes) -> str:
        captured: list[str] = []

        async def run() -> None:
            with (
                patch.object(server, "_require_crew", return_value=self.CREW),
                patch.object(server, "_ensure_crew_running", return_value=self.CREW),
                patch.object(server, "_async_http") as fake_http,
            ):
                request = _FakeStreamRequest(
                    path="/crews/demo/api/search",
                    query_string=query_string,
                )

                class HTTPRequestCapture:
                    async def request(self_inner, method, url, **kwargs):
                        captured.append(url)
                        response = Mock()
                        response.status_code = 200
                        response.content = b"ok"
                        response.headers = {}
                        return response

                fake_http.request = HTTPRequestCapture().request
                await server._handle_crew_api_proxy(request)

        asyncio.run(run())
        self.assertEqual(len(captured), 1)
        return captured[0]

    def test_ui_proxy_strips_cr_lf_and_null(self) -> None:
        query = b"q=hello\r\nworld\x00&limit=10"
        self.assertEqual(
            self._capture_dashboard_url(query),
            "http://gs-demo:5476/search?q=helloworld&limit=10",
        )

    def test_api_proxy_strips_cr_lf_and_null(self) -> None:
        query = b"q=hello\r\nworld\x00&limit=10"
        self.assertEqual(
            self._capture_api_url(query),
            "http://gs-demo:5476/api/search?q=helloworld&limit=10",
        )

    def test_ui_proxy_preserves_ordinary_and_percent_encoded_queries(self) -> None:
        for query in (b"q=hello&limit=10", b"q=hello%0Aworld&limit=10"):
            with self.subTest(query=query):
                self.assertEqual(
                    self._capture_dashboard_url(query),
                    f"http://gs-demo:5476/search?{query.decode('ascii')}",
                )

    def test_api_proxy_preserves_ordinary_and_percent_encoded_queries(self) -> None:
        for query in (b"q=hello&limit=10", b"q=hello%0Aworld&limit=10"):
            with self.subTest(query=query):
                self.assertEqual(
                    self._capture_api_url(query),
                    f"http://gs-demo:5476/api/search?{query.decode('ascii')}",
                )

    def test_helper_strips_full_ascii_control_range_and_preserves_latin1(self) -> None:
        controls = bytes(range(0x20)) + bytes((0x7F,))
        high_bytes = bytes((0x80, 0xFF))
        raw = b"before" + controls + high_bytes + b"after%0A"

        self.assertEqual(
            server._sanitise_query_string(raw),
            "before" + high_bytes.decode("latin-1") + "after%0A",
        )
