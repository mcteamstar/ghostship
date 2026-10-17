"""Unit tests for TRN-233 task 3.2: pasted-secret routes, GET status, and logout handlers.

Covers:
- POST /login/{backend}/api-key and setup-token: store credential and return status
- Empty-secret 400 response
- Disabled-backend 400 response
- GET /login/{backend}: status with no secret values
- POST /logout/{backend}: idempotent, clears credential store entry
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import types
import unittest
from unittest.mock import patch

from tests.fakes import FakePodmanClient
from transport.credentials import CredentialStore


# ── Minimal async request/response helpers ────────────────────────────────────

def _make_request(body: dict | None = None, json_body: bool = True) -> object:
    """Build a minimal stub of starlette.requests.Request with async json()."""
    req = types.SimpleNamespace()
    if body is not None and json_body:
        import json as _json
        body_bytes = _json.dumps(body).encode()

        async def json_method():
            return _json.loads(body_bytes)

        req.json = json_method
    else:
        async def json_method():
            raise Exception("No body")
        req.json = json_method

    # For handlers that call _request_source
    req.scope = {"type": "http", "client": ("127.0.0.1", 12345)}
    return req


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _json_data(response) -> dict:
    """Extract JSON dict from a JSONResponse stub."""
    if hasattr(response, "data"):
        return response.data
    body = getattr(response, "body", b"")
    return json.loads(body)


class _BaseRouteTest(unittest.TestCase):
    """Base class that sets up a temp credential store and patches _cred_store."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._store = CredentialStore(self._tmp.name)
        import transport.login as login_mod
        self._orig_store = login_mod._cred_store
        login_mod._cred_store = self._store

    def tearDown(self) -> None:
        import transport.login as login_mod
        login_mod._cred_store = self._orig_store
        self._tmp.cleanup()


# ── Tests for POST /login/{backend}/api-key ───────────────────────────────────

class TestPastedSecretRoutes(_BaseRouteTest):
    """POST /login/{backend}/api-key and /login/claude/setup-token store via the store."""

    def setUp(self) -> None:
        super().setUp()
        import transport.login as login_mod
        from transport.config import Config
        self._orig_cfg = login_mod.cfg
        # Enable all backends for these tests
        login_mod.cfg = Config(ga_crew_agent="kiro,claude,codex")

    def tearDown(self) -> None:
        import transport.login as login_mod
        login_mod.cfg = self._orig_cfg
        super().tearDown()

    def test_kiro_api_key_stored(self):
        from transport.login import _handle_login_kiro_api_key_post
        req = _make_request({"secret": "kiro-api-key-value-here"})
        with patch("transport.login._security") as mock_sec:
            mock_sec.audit_auth_event = lambda **kw: None
            resp = _run(_handle_login_kiro_api_key_post(req))
        self.assertEqual(resp.status_code, 200)
        data = _json_data(resp)
        self.assertEqual(data["status"], "stored")
        self.assertEqual(data["backend"], "kiro")
        self.assertEqual(data["method"], "api-key")
        # Confirm the store holds the credential
        cred = self._store.get("kiro")
        self.assertIsNotNone(cred)
        self.assertEqual(cred["method"], "api-key")
        self.assertEqual(cred["payload"], b"kiro-api-key-value-here")

    def test_claude_api_key_stored(self):
        from transport.login import _handle_login_claude_api_key_post
        req = _make_request({"secret": "sk-ant-api-key-test"})
        with patch("transport.login._security") as mock_sec:
            mock_sec.audit_auth_event = lambda **kw: None
            resp = _run(_handle_login_claude_api_key_post(req))
        self.assertEqual(resp.status_code, 200)
        cred = self._store.get("claude")
        self.assertEqual(cred["method"], "api-key")

    def test_claude_setup_token_stored(self):
        from transport.login import _handle_login_claude_setup_token_post
        req = _make_request({"secret": "setup-token-test-value"})
        with patch("transport.login._security") as mock_sec:
            mock_sec.audit_auth_event = lambda **kw: None
            resp = _run(_handle_login_claude_setup_token_post(req))
        self.assertEqual(resp.status_code, 200)
        data = _json_data(resp)
        self.assertEqual(data["method"], "setup-token")
        cred = self._store.get("claude")
        self.assertEqual(cred["method"], "setup-token")

    def test_codex_api_key_stored(self):
        from transport.login import _handle_login_codex_api_key_post
        req = _make_request({"secret": "sk-openai-test"})
        with patch("transport.login._security") as mock_sec:
            mock_sec.audit_auth_event = lambda **kw: None
            resp = _run(_handle_login_codex_api_key_post(req))
        self.assertEqual(resp.status_code, 200)
        cred = self._store.get("codex")
        self.assertEqual(cred["method"], "api-key")

    def test_status_has_stored_at_but_no_payload(self):
        """The store response includes stored_at but never the secret value."""
        from transport.login import _handle_login_claude_api_key_post
        req = _make_request({"secret": "super-secret-key-value-here"})
        with patch("transport.login._security") as mock_sec:
            mock_sec.audit_auth_event = lambda **kw: None
            resp = _run(_handle_login_claude_api_key_post(req))
        data = _json_data(resp)
        # stored_at must be in the response
        self.assertIn("stored_at", data)
        # Secret value must not be in the response
        raw = resp.body.decode() if isinstance(resp.body, bytes) else str(data)
        self.assertNotIn("super-secret-key-value-here", raw)


class TestEmptySecretReturns400(_BaseRouteTest):
    """Empty or missing secret returns 400."""

    def test_kiro_api_key_empty_string(self):
        from transport.login import _handle_login_kiro_api_key_post
        req = _make_request({"secret": ""})
        resp = _run(_handle_login_kiro_api_key_post(req))
        self.assertEqual(resp.status_code, 400)

    def test_kiro_api_key_whitespace_only(self):
        from transport.login import _handle_login_kiro_api_key_post
        req = _make_request({"secret": "   "})
        resp = _run(_handle_login_kiro_api_key_post(req))
        self.assertEqual(resp.status_code, 400)

    def test_kiro_api_key_missing_field(self):
        from transport.login import _handle_login_kiro_api_key_post
        req = _make_request({"other": "value"})
        resp = _run(_handle_login_kiro_api_key_post(req))
        self.assertEqual(resp.status_code, 400)

    def test_claude_api_key_empty(self):
        from transport.login import _handle_login_claude_api_key_post
        req = _make_request({"secret": ""})
        resp = _run(_handle_login_claude_api_key_post(req))
        self.assertEqual(resp.status_code, 400)

    def test_codex_api_key_empty(self):
        from transport.login import _handle_login_codex_api_key_post
        req = _make_request({"secret": ""})
        resp = _run(_handle_login_codex_api_key_post(req))
        self.assertEqual(resp.status_code, 400)


class TestDisabledBackendReturns400(_BaseRouteTest):
    """Login routes return 400 when the backend is not enabled."""

    def test_claude_api_key_disabled_backend(self):
        from transport.login import _handle_login_claude_api_key_post
        from transport.config import Config
        import transport.login as login_mod
        orig_cfg = login_mod.cfg
        try:
            login_mod.cfg = Config(ga_crew_agent="kiro")
            req = _make_request({"secret": "sk-ant-key"})
            resp = _run(_handle_login_claude_api_key_post(req))
            self.assertEqual(resp.status_code, 400)
        finally:
            login_mod.cfg = orig_cfg

    def test_codex_api_key_disabled_backend(self):
        from transport.login import _handle_login_codex_api_key_post
        from transport.config import Config
        import transport.login as login_mod
        orig_cfg = login_mod.cfg
        try:
            login_mod.cfg = Config(ga_crew_agent="kiro")
            req = _make_request({"secret": "sk-openai-key"})
            resp = _run(_handle_login_codex_api_key_post(req))
            self.assertEqual(resp.status_code, 400)
        finally:
            login_mod.cfg = orig_cfg


class TestGetLoginStatus(_BaseRouteTest):
    """GET /login/{backend} returns status with no secret values."""

    def test_kiro_get_unconfigured(self):
        from transport.login import _handle_login_kiro_get
        req = _make_request()
        resp = _run(_handle_login_kiro_get(req))
        self.assertEqual(resp.status_code, 200)
        data = _json_data(resp)
        self.assertFalse(data["configured"])
        self.assertIsNone(data["method"])
        self.assertIsNone(data["pending_flow"])

    def test_kiro_get_configured(self):
        self._store.put("kiro", "api-key", "kiro-secret-key-value")
        from transport.login import _handle_login_kiro_get
        req = _make_request()
        resp = _run(_handle_login_kiro_get(req))
        data = _json_data(resp)
        self.assertTrue(data["configured"])
        self.assertEqual(data["method"], "api-key")
        # Secret value must not appear
        raw = resp.body.decode() if isinstance(resp.body, bytes) else json.dumps(data)
        self.assertNotIn("kiro-secret-key-value", raw)

    def test_claude_get_unconfigured(self):
        from transport.login import _handle_login_claude_get_new
        req = _make_request()
        resp = _run(_handle_login_claude_get_new(req))
        data = _json_data(resp)
        self.assertFalse(data["configured"])

    def test_codex_get_unconfigured(self):
        from transport.login import _handle_login_codex_get_new
        req = _make_request()
        resp = _run(_handle_login_codex_get_new(req))
        data = _json_data(resp)
        self.assertFalse(data["configured"])

    def test_status_no_payload_anywhere(self):
        """GET /login/{backend} must never expose secret values in the response."""
        self._store.put("claude", "api-key", "sk-ant-super-secret-key")
        from transport.login import _handle_login_claude_get_new
        req = _make_request()
        resp = _run(_handle_login_claude_get_new(req))
        raw = resp.body.decode() if isinstance(resp.body, bytes) else ""
        self.assertNotIn("sk-ant-super-secret-key", raw)


class TestLogoutCredentialStore(_BaseRouteTest):
    """POST /logout/{backend} clears the credential store and is idempotent."""

    def _patch_lifecycle(self):
        """Return a context manager that patches _lc() helpers used by logout."""
        import unittest.mock
        return unittest.mock.patch.multiple(
            "transport.login",
            _get_podman=lambda: FakePodmanClient(),
            _security=types.SimpleNamespace(
                audit_auth_event=lambda **kw: None,
            ),
        )

    def test_logout_kiro_clears_credential_store(self):
        self._store.put("kiro", "api-key", "kiro-key-to-delete")
        self.assertIsNotNone(self._store.get("kiro"))

        from transport.login import _handle_logout_kiro_post
        req = _make_request()
        # _handle_logout_kiro_post also delegates to _handle_logout_post
        # which reads ga-kiro-auth — patch to avoid filesystem access
        with patch("transport.login._lc") as mock_lc:
            lc = types.SimpleNamespace(
                _read_auth_file=lambda: None,
                _auth_file_path=lambda: types.SimpleNamespace(
                    unlink=lambda missing_ok=False: None
                ),
                _inject_auth=lambda *a, **kw: None,
            )
            mock_lc.return_value = lc
            with patch("transport.login._security") as mock_sec:
                mock_sec.audit_auth_event = lambda **kw: None
                with patch("transport.login._get_podman", return_value=FakePodmanClient()):
                    with patch("transport.login.registry") as mock_reg:
                        mock_reg._reg = {"crews": {}}
                        mock_reg.__enter__ = lambda s: s
                        mock_reg.__exit__ = lambda s, *a: None
                        resp = _run(_handle_logout_kiro_post(req))

        # Credential store entry should be gone
        self.assertIsNone(self._store.get("kiro"))

    def test_logout_claude_clears_credential_store(self):
        self._store.put("claude", "api-key", "sk-ant-to-delete")
        from transport.login import _handle_logout_claude_post_new
        req = _make_request()
        with patch("transport.login._lc") as mock_lc:
            lc = types.SimpleNamespace(
                _claude_auth_exists=lambda: False,
                _codex_auth_exists=lambda: False,
                _abort_claude_pending_login=lambda podman: False,
            )
            mock_lc.return_value = lc
            with patch("transport.login._security") as mock_sec:
                mock_sec.audit_auth_event = lambda **kw: None
                with patch("transport.login._get_podman", return_value=FakePodmanClient()):
                    with patch("transport.login.registry") as mock_reg:
                        mock_reg._reg = {"crews": {}}
                        mock_reg.__enter__ = lambda s: s
                        mock_reg.__exit__ = lambda s, *a: None
                        resp = _run(_handle_logout_claude_post_new(req))

        self.assertIsNone(self._store.get("claude"))

    def test_logout_codex_clears_credential_store(self):
        self._store.put("codex", "api-key", "sk-openai-to-delete")
        from transport.login import _handle_logout_codex_post_new
        req = _make_request()
        with patch("transport.login._lc") as mock_lc:
            lc = types.SimpleNamespace(
                _codex_auth_exists=lambda: False,
                _abort_codex_pending_login=lambda podman: False,
            )
            mock_lc.return_value = lc
            with patch("transport.login._security") as mock_sec:
                mock_sec.audit_auth_event = lambda **kw: None
                with patch("transport.login._get_podman", return_value=FakePodmanClient()):
                    with patch("transport.login.registry") as mock_reg:
                        mock_reg._reg = {"crews": {}}
                        mock_reg.__enter__ = lambda s: s
                        mock_reg.__exit__ = lambda s, *a: None
                        resp = _run(_handle_logout_codex_post_new(req))

        self.assertIsNone(self._store.get("codex"))

    def test_logout_kiro_idempotent_no_credential(self):
        """Logout with no stored credential returns without error."""
        self.assertIsNone(self._store.get("kiro"))
        from transport.login import _handle_logout_kiro_post
        req = _make_request()
        with patch("transport.login._lc") as mock_lc:
            lc = types.SimpleNamespace(
                _read_auth_file=lambda: None,
                _auth_file_path=lambda: types.SimpleNamespace(
                    unlink=lambda missing_ok=False: None
                ),
                _inject_auth=lambda *a, **kw: None,
            )
            mock_lc.return_value = lc
            with patch("transport.login._security") as mock_sec:
                mock_sec.audit_auth_event = lambda **kw: None
                with patch("transport.login._get_podman", return_value=FakePodmanClient()):
                    with patch("transport.login.registry") as mock_reg:
                        mock_reg._reg = {"crews": {}}
                        mock_reg.__enter__ = lambda s: s
                        mock_reg.__exit__ = lambda s, *a: None
                        # Should not raise
                        resp = _run(_handle_logout_kiro_post(req))
        # delete on an already-empty store is safe
        self.assertIsNone(self._store.get("kiro"))


if __name__ == "__main__":
    unittest.main()
