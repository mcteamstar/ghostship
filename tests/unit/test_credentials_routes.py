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
import os
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


class TestKiroDeviceFlowRoutesPassMethod(_BaseRouteTest):
    """The kiro device-flow routes hand their method/provider to the PTY flow."""

    def _call(self, handler_name, body):
        import transport.login as login_mod
        from transport.config import Config
        orig_cfg = login_mod.cfg
        calls = []

        async def fake_login_post(request, method=None, provider=None):
            calls.append({"method": method, "provider": provider})
            return login_mod.JSONResponse({"status": "pending"})

        try:
            login_mod.cfg = Config(
                ga_crew_agent="kiro",
                kiro_identity_provider="https://cfg.awsapps.com/start/#/",
                kiro_region="us-east-1",
            )
            with patch.object(login_mod, "_handle_login_post", fake_login_post):
                _run(getattr(login_mod, handler_name)(_make_request(body)))
        finally:
            login_mod.cfg = orig_cfg
        return calls

    def test_identity_center_uses_request_values(self):
        calls = self._call(
            "_handle_login_kiro_identity_center_post",
            {"start_url": "https://req.awsapps.com/start/#/", "region": "eu-west-1"},
        )
        self.assertEqual(calls, [{
            "method": "identity-center",
            "provider": {"start_url": "https://req.awsapps.com/start/#/", "region": "eu-west-1"},
        }])

    def test_identity_center_falls_back_to_config(self):
        calls = self._call("_handle_login_kiro_identity_center_post", {})
        self.assertEqual(calls[0]["provider"], {
            "start_url": "https://cfg.awsapps.com/start/#/", "region": "us-east-1",
        })

    def test_builder_id_does_not_use_identity_center(self):
        calls = self._call("_handle_login_kiro_builder_id_post", {})
        self.assertEqual(calls, [{"method": "builder-id", "provider": None}])


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

    def test_kiro_get_identity_center_defaults(self):
        """Spec: GET /login/kiro exposes configured Identity Center defaults as
        identity_center.start_url / identity_center.region."""
        import transport.login as login_mod
        from transport.config import Config
        orig_cfg = login_mod.cfg
        try:
            login_mod.cfg = Config(
                ga_crew_agent="kiro",
                kiro_identity_provider="https://my-sso.awsapps.com/start",
                kiro_region="us-east-1",
            )
            from transport.login import _handle_login_kiro_get
            resp = _run(_handle_login_kiro_get(_make_request()))
            data = _json_data(resp)
            self.assertIn("identity_center", data)
            self.assertEqual(
                data["identity_center"]["start_url"],
                "https://my-sso.awsapps.com/start",
            )
            self.assertEqual(data["identity_center"]["region"], "us-east-1")
        finally:
            login_mod.cfg = orig_cfg

    def test_kiro_get_identity_center_defaults_while_flow_pending(self):
        """A pending (possibly stale) flow must not hide the IDC defaults."""
        import transport.login as login_mod
        from transport.config import Config
        orig_cfg = login_mod.cfg
        orig_pending = login_mod.KIRO_FLOW._pending

        async def fake_poll(request):
            return login_mod.JSONResponse({"status": "pending"})

        try:
            login_mod.cfg = Config(
                ga_crew_agent="kiro",
                kiro_identity_provider="https://my-sso.awsapps.com/start",
                kiro_region="us-east-1",
            )
            login_mod.KIRO_FLOW._pending = {"container": "ga-login-x", "started_at": 0}
            with patch.object(login_mod, "_handle_login_get", fake_poll):
                resp = _run(login_mod._handle_login_kiro_get(_make_request()))
            data = _json_data(resp)
            self.assertEqual(data["status"], "pending")
            self.assertEqual(data["identity_center"]["region"], "us-east-1")
        finally:
            login_mod.cfg = orig_cfg
            login_mod.KIRO_FLOW._pending = orig_pending

    def test_kiro_get_no_identity_center_when_unconfigured(self):
        """No identity_center block when KIRO_IDENTITY_PROVIDER/KIRO_REGION unset."""
        from transport.login import _handle_login_kiro_get
        resp = _run(_handle_login_kiro_get(_make_request()))
        self.assertNotIn("identity_center", _json_data(resp))

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


class _LogoutHarness(_BaseRouteTest):
    """Drives the three /logout/{backend} routes against temp paths.

    ``_lc`` is replaced with a stub whose legacy auth paths live in the temp
    directory, so nothing under DATA_DIR is touched. The abort helpers are
    stubs that record calls; ``abort_result`` sets what each one reports.
    """

    ROUTES = {
        "kiro": "_handle_logout_kiro_post",
        "claude": "_handle_logout_claude_post_new",
        "codex": "_handle_logout_codex_post_new",
    }
    ACCOUNTS = {"kiro": "academy", "claude": "claude", "codex": "codex"}

    def setUp(self) -> None:
        super().setUp()
        import transport.login as login_mod
        self._login = login_mod
        self.podman = FakePodmanClient()
        base = self._tmp.name
        self.legacy = {
            "kiro": os.path.join(base, "ga-kiro-auth"),
            "claude": os.path.join(base, "ga-claude-auth"),
            "codex": os.path.join(base, "ga-codex-auth"),
        }
        self.abort_calls: list[str] = []
        self.abort_result: dict[str, bool] = {}
        self.audits: list[tuple] = []
        self.crews: dict = {}

        def _abort(name):
            def _call(podman):
                self.abort_calls.append(name)
                return self.abort_result.get(name, False)
            return _call

        lc = types.SimpleNamespace(
            _abort_pending_login=_abort("kiro"),
            _abort_claude_pending_login=_abort("claude"),
            _abort_codex_pending_login=_abort("codex"),
            _auth_file_path=lambda: types.SimpleNamespace(unlink=_unlinker(self.legacy["kiro"])),
            _claude_auth_file_path=lambda: types.SimpleNamespace(unlink=_unlinker(self.legacy["claude"])),
            _codex_auth_file_path=lambda: types.SimpleNamespace(unlink=_unlinker(self.legacy["codex"])),
        )
        for name, value in (
            ("_lc", lambda: lc),
            ("_get_podman", lambda: self.podman),
            ("_request_source", lambda request: None),
            ("_security", types.SimpleNamespace(
                audit_auth_event=lambda **kw: self.audits.append(
                    (kw["action"], kw["outcome"], kw["account"])
                ),
            )),
            ("registry", _FakeRegistry(self.crews)),
        ):
            patcher = patch.object(login_mod, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _logout(self, backend: str):
        import transport.login as login_mod
        handler = getattr(login_mod, self.ROUTES[backend])
        return _run(handler(_make_request()))

    def _write_legacy(self, backend: str) -> None:
        with open(self.legacy[backend], "w") as f:
            f.write("legacy-device-credential")


def _unlinker(path: str):
    """Return an ``unlink`` that removes *path* the way pathlib would, raising like it."""
    def _unlink(missing_ok: bool = False):
        os.unlink(path)
    return _unlink


class TestLogoutCancelsAndClears(_LogoutHarness):
    """POST /logout/{backend}: cancel any pending login, remove the credential, idempotent."""

    def test_pending_flow_with_nothing_stored_is_cancelled(self):
        for backend in ("kiro", "claude", "codex"):
            with self.subTest(backend=backend):
                self.abort_calls.clear()
                self.audits.clear()
                self.abort_result = {backend: True}
                resp = self._logout(backend)
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(_json_data(resp), {"status": "logged_out", "aborted_pending_login": True})
                self.assertEqual(self.abort_calls, [backend])
                self.assertEqual(self.audits, [])

    def test_nothing_pending_or_stored_is_idempotent_and_silent(self):
        for backend in ("kiro", "claude", "codex"):
            with self.subTest(backend=backend):
                self.audits.clear()
                resp = self._logout(backend)
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(_json_data(resp), {"status": "logged_out"})
                self.assertEqual(self.audits, [])

    def test_store_only_credentials_are_removed(self):
        cases = (
            ("kiro", "api-key", "kiro-key"),
            ("claude", "setup-token", "claude-token"),
            ("codex", "api-key", "sk-openai"),
        )
        for backend, method, secret in cases:
            with self.subTest(backend=backend, method=method):
                self.audits.clear()
                self._store.put(backend, method, secret)
                resp = self._logout(backend)
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(_json_data(resp), {"status": "logged_out"})
                self.assertIsNone(self._store.get(backend))
                self.assertEqual(self.audits, [("logout", "success", self.ACCOUNTS[backend])])

    def test_legacy_device_credential_file_is_removed(self):
        for backend in ("kiro", "claude", "codex"):
            with self.subTest(backend=backend):
                self._write_legacy(backend)
                resp = self._logout(backend)
                self.assertEqual(resp.status_code, 200)
                self.assertFalse(os.path.exists(self.legacy[backend]))

    def test_pending_flow_and_store_credential_both_cleared(self):
        self._store.put("claude", "oauth", b"tar-bytes")
        self.abort_result = {"claude": True}
        resp = self._logout("claude")
        self.assertEqual(_json_data(resp), {"status": "logged_out", "aborted_pending_login": True})
        self.assertEqual(self.abort_calls, ["claude"])
        self.assertIsNone(self._store.get("claude"))

    def test_store_delete_failure_is_500_and_audited_as_failure(self):
        self._store.put("codex", "api-key", "sk-openai")
        with patch.object(self._store, "delete", side_effect=PermissionError("denied")):
            resp = self._logout("codex")
        self.assertEqual(resp.status_code, 500)
        body = _json_data(resp)
        self.assertEqual(body["status"], "error")
        self.assertIsNotNone(self._store.get("codex"))
        self.assertEqual(self.audits, [("logout", "failure", "codex")])

    def test_podman_unavailable_still_removes_credential_and_reports_500(self):
        import transport.login as login_mod
        self._store.put("kiro", "api-key", "sk-kiro")
        self._write_legacy("kiro")
        with patch.object(login_mod, "_get_podman", side_effect=RuntimeError("no podman socket")):
            resp = self._logout("kiro")
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(_json_data(resp)["status"], "error")
        self.assertIsNone(self._store.get("kiro"))
        self.assertFalse(os.path.exists(self.legacy["kiro"]))
        self.assertEqual(self.abort_calls, [])

    def test_legacy_file_removal_failure_is_500(self):
        # A directory at the legacy path cannot be unlinked, so the removal fails.
        os.mkdir(self.legacy["kiro"])
        resp = self._logout("kiro")
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(_json_data(resp)["status"], "error")
        self.assertEqual(self.audits, [("logout", "failure", "academy")])


class TestLogoutLeavesRunningCrews(_LogoutHarness):
    """POST /logout/{backend} never executes into, restarts or stops a running crew (TRN-258)."""

    def test_running_crews_of_each_backend_are_untouched(self):
        self.crews.update({
            "kiro-run": {"status": "running", "container": "gs-crew-kiro", "acp_backend": "kiro"},
            "claude-run": {"status": "running", "container": "gs-crew-claude", "acp_backend": "claude"},
            "codex-run": {"status": "running", "container": "gs-crew-codex", "acp_backend": "codex"},
        })
        before = {cid: dict(info) for cid, info in self.crews.items()}
        self._store.put("kiro", "builder-id", "rows")
        self._write_legacy("claude")
        for backend in ("kiro", "claude", "codex"):
            resp = self._logout(backend)
            self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.podman.calls, [])
        self.assertEqual(self.crews, before)


class TestNewLoginAfterCancel(_LogoutHarness):
    """A login started after a cancelling logout is a new flow, not a 409 (TRN-258)."""

    def test_initiate_after_logout_cancel_is_not_refused_as_pending(self):
        import transport.login as login_mod
        flow = login_mod.KIRO_FLOW
        flow._pending = {"container": None, "state": "starting", "started_at": 0.0}
        self.addCleanup(setattr, flow, "_pending", None)
        # Real abort, not a stub, so this exercises the real cancel path.
        with patch.object(login_mod, "_lc", lambda: types.SimpleNamespace(
            _abort_pending_login=lambda podman: flow.abort(podman),
            _auth_file_path=lambda: types.SimpleNamespace(unlink=_unlinker(self.legacy["kiro"])),
        )):
            resp = self._logout("kiro")
        self.assertEqual(_json_data(resp), {"status": "logged_out", "aborted_pending_login": True})
        self.assertIsNone(flow.state)

        class _Stop(login_mod.KiroLoginFlow):
            def start_container(self, podman):
                raise RuntimeError("stop here")

        result = _Stop().initiate(FakePodmanClient())
        self.assertNotIn("login_pending", result)
        self.assertIn("error", result)


class _FakeRegistry:
    """Stands in for transport.login.registry: a context manager over a crews dict."""

    def __init__(self, crews: dict) -> None:
        self._reg = {"crews": crews}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestCompletionCommitsOnlyWhileCurrent(_BaseRouteTest):
    """Completion GETs store a credential only while their flow is still pending (TRN-258)."""

    def setUp(self) -> None:
        super().setUp()
        import time
        import transport.login as login_mod
        self._time = time
        self.podman = FakePodmanClient()
        self.written: list[tuple] = []
        self.injected: list[str] = []
        self.crews: dict = {}
        self.lc = types.SimpleNamespace(
            _read_auth_from_crew=lambda podman, container: None,
            _write_auth_file=lambda value: self.written.append(("kiro", value)),
            _inject_auth=lambda podman, container, auth_b64: self.injected.append(container),
            _write_claude_auth_file=lambda data: self.written.append(("claude", data)),
            _write_codex_auth_file=lambda data: self.written.append(("codex", data)),
        )
        for name, value in (
            ("_get_podman", lambda: self.podman),
            ("_security", types.SimpleNamespace(audit_auth_event=lambda **kw: None)),
            ("_request_source", lambda request: None),
            ("registry", _FakeRegistry(self.crews)),
            ("_lc", lambda: self.lc),
        ):
            patcher = patch.object(login_mod, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for flow in (login_mod.KIRO_FLOW, login_mod.CLAUDE_FLOW, login_mod.CODEX_FLOW):
            self.addCleanup(setattr, flow, "_pending", None)
            flow._pending = None

    def _pending(self, container: str, state: str = "started") -> dict:
        return {"container": container, "state": state, "started_at": self._time.time()}

    def test_kiro_completion_cancelled_by_logout_stores_nothing(self):
        import transport.login as login_mod
        login_mod.KIRO_FLOW._pending = self._pending("ga-login-k1")
        self.crews["k-1"] = {"status": "running", "container": "c-k1", "acp_backend": "kiro"}

        def poll_then_logout(podman, container):
            # Logout's abort lands between the poll and the commit.
            login_mod.KIRO_FLOW.abort(podman)
            return "kiro-auth-rows"

        self.lc._read_auth_from_crew = poll_then_logout
        from transport.login import _handle_login_get, _handle_login_kiro_get
        resp = _run(_handle_login_get(_make_request()))
        self.assertEqual(_json_data(resp), {"status": "cancelled"})
        self.assertIsNone(self._store.get("kiro"))
        self.assertEqual(self.written, [])
        self.assertEqual(self.injected, [])
        status = _json_data(_run(_handle_login_kiro_get(_make_request())))
        self.assertIsNone(status["pending_flow"])
        self.assertFalse(status["configured"])

    def test_kiro_completion_injects_only_into_kiro_crews(self):
        import transport.login as login_mod
        login_mod.KIRO_FLOW._pending = self._pending("ga-login-k2")
        self.lc._read_auth_from_crew = lambda podman, container: "kiro-auth-rows"
        self.crews.update({
            "kiro-run": {"status": "running", "container": "c-kiro", "acp_backend": "kiro"},
            "no-field": {"status": "running", "container": "c-nofield"},
            "claude-run": {"status": "running", "container": "c-claude", "acp_backend": "claude"},
            "codex-run": {"status": "running", "container": "c-codex", "acp_backend": "codex"},
        })
        from transport.login import _handle_login_get
        resp = _run(_handle_login_get(_make_request()))
        self.assertEqual(_json_data(resp), {"status": "complete"})
        self.assertEqual(sorted(self.injected), ["c-kiro", "c-nofield"])
        self.assertEqual(self._store.get("kiro")["method"], "builder-id")
        self.assertIsNone(login_mod.KIRO_FLOW.state)

    def test_claude_completion_cancelled_by_logout_stores_nothing(self):
        import transport.login as login_mod
        login_mod.CLAUDE_FLOW._pending = self._pending("ga-claude-login-c1", "awaiting_code")

        def poll_then_logout(podman):
            login_mod.CLAUDE_FLOW.abort(podman)
            return b"tar-bytes"

        from transport.login import _handle_claude_login_get
        with patch.object(login_mod.CLAUDE_FLOW, "poll", side_effect=poll_then_logout):
            resp = _run(_handle_claude_login_get(_make_request()))
        self.assertEqual(_json_data(resp), {"status": "cancelled"})
        self.assertIsNone(self._store.get("claude"))
        self.assertEqual(self.written, [])
        self.assertIsNone(login_mod.CLAUDE_FLOW.state)

    def test_claude_completion_commits_when_current(self):
        import transport.login as login_mod
        login_mod.CLAUDE_FLOW._pending = self._pending("ga-claude-login-c2", "awaiting_code")
        from transport.login import _handle_claude_login_get
        with patch.object(login_mod.CLAUDE_FLOW, "poll", return_value=b"tar-bytes"):
            resp = _run(_handle_claude_login_get(_make_request()))
        self.assertEqual(_json_data(resp), {"status": "complete"})
        self.assertEqual(self._store.get("claude")["method"], "oauth")
        self.assertEqual(self.written, [("claude", b"tar-bytes")])
        self.assertIsNone(login_mod.CLAUDE_FLOW.state)

    def test_codex_completion_cancelled_by_logout_writes_nothing(self):
        import transport.login as login_mod
        login_mod.CODEX_FLOW._pending = self._pending("ga-codex-login-c1")

        def poll_then_logout(podman):
            login_mod.CODEX_FLOW.abort(podman)
            return b"tar-bytes"

        from transport.login import _handle_codex_login_get
        with patch.object(login_mod.CODEX_FLOW, "poll", side_effect=poll_then_logout):
            resp = _run(_handle_codex_login_get(_make_request()))
        self.assertEqual(_json_data(resp), {"status": "cancelled"})
        self.assertEqual(self.written, [])
        self.assertIsNone(login_mod.CODEX_FLOW.state)


if __name__ == "__main__":
    unittest.main()
