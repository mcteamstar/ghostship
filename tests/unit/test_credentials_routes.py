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

def _make_request(body: dict | None = None, json_body: bool = True,
                  query_params: dict | None = None) -> object:
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
    # For handlers that read profile from query params
    req.query_params = query_params or {}
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

    def test_login_commit_waits_for_older_logout_to_finish(self):
        import threading
        flow = self._login.CODEX_FLOW
        pending = {"container": "login-test", "state": "started", "profile": "work"}
        flow._pending = pending
        self.addCleanup(setattr, flow, "_pending", None)
        entered, release, committed = threading.Event(), threading.Event(), threading.Event()
        real_delete = self._store.delete

        def delayed_delete(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(5))
            return real_delete(*args, **kwargs)

        def complete():
            flow.commit_if_current(pending, lambda: self._store.put("codex", "api-key", "new-fixture", profile="work"))
            committed.set()

        with patch.object(self._store, "delete", side_effect=delayed_delete):
            logout = threading.Thread(target=lambda: self._login._logout("codex", _make_request()))
            logout.start()
            self.assertTrue(entered.wait(5))
            login = threading.Thread(target=complete)
            login.start()
            self.assertFalse(committed.wait(0.1))
            release.set()
            logout.join(5)
            login.join(5)
        self.assertTrue(committed.is_set())
        self.assertEqual(self._store.get("codex", "work")["payload"], b"new-fixture")

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

    def test_named_oauth_completion_does_not_write_legacy_archive(self):
        import base64
        import transport.login as login_mod
        for flow, handler, backend, method in (
            (login_mod.CLAUDE_FLOW, login_mod._handle_claude_login_get, "claude", "oauth"),
            (login_mod.CODEX_FLOW, login_mod._handle_codex_login_get, "codex", "chatgpt"),
        ):
            with self.subTest(backend=backend):
                flow._pending = {**self._pending("login-container"), "profile": "work"}
                with patch.object(flow, "poll", return_value=b"synthetic archive"):
                    resp = _run(handler(_make_request()))
                self.assertEqual(_json_data(resp), {"status": "complete"})
                self.assertEqual(self._store.get(backend, "work")["method"], method)
                self.assertEqual(base64.b64decode(self._store.get(backend, "work")["payload"]), b"synthetic archive")
                self.assertEqual(self.written, [])

    def test_oauth_store_failure_keeps_pending_flow(self):
        import transport.login as login_mod
        for flow, handler in (
            (login_mod.CLAUDE_FLOW, login_mod._handle_claude_login_get),
            (login_mod.CODEX_FLOW, login_mod._handle_codex_login_get),
        ):
            with self.subTest(flow=type(flow).__name__):
                flow._pending = {**self._pending("login-container"), "profile": "work"}
                with patch.object(flow, "poll", return_value=b"synthetic archive"), patch.object(self._store, "put", side_effect=OSError("write failed")):
                    resp = _run(handler(_make_request()))
                self.assertEqual(resp.status_code, 500)
                self.assertIsNotNone(flow.state)
                self.assertEqual(self.written, [])

    def test_oauth_store_failure_does_not_expose_exception_secret(self):
        import transport.login as login_mod
        marker = "synthetic-sensitive-marker"
        flow = login_mod.CODEX_FLOW
        flow._pending = {**self._pending("login-container"), "profile": "work"}
        with self.assertLogs(login_mod.logger, level="ERROR") as captured, \
             patch.object(flow, "poll", return_value=b"synthetic archive"), \
             patch.object(self._store, "put", side_effect=OSError(marker)):
            resp = _run(login_mod._handle_codex_login_get(_make_request()))
        self.assertEqual(resp.status_code, 500)
        self.assertNotIn(marker, resp.body.decode())
        self.assertNotIn(marker, " ".join(captured.output))

    def test_codex_rotation_only_updates_matching_profile_crews(self):
        import transport.login as login_mod
        sent = []
        self.lc._inject_codex_auth = lambda podman, container, data: sent.append((container, data))
        self.crews.update({
            "selected": {"status": "running", "container": "c-selected", "acp_backend": "codex", "acp_profile": "work"},
            "other": {"status": "running", "container": "c-other", "acp_backend": "codex", "acp_profile": "personal"},
            "stopped": {"status": "stopped", "container": "c-stopped", "acp_backend": "codex", "acp_profile": "work"},
            "other-backend": {"status": "running", "container": "c-claude", "acp_backend": "claude", "acp_profile": "work"},
        })
        login_mod.CODEX_FLOW._pending = {**self._pending("login-container"), "profile": "work"}
        with patch.object(login_mod.CODEX_FLOW, "poll", return_value=b"synthetic archive"):
            resp = _run(login_mod._handle_codex_login_get(_make_request()))
        self.assertEqual(_json_data(resp), {"status": "complete"})
        self.assertEqual(sent, [("c-selected", b"synthetic archive")])

    def test_named_kiro_completion_does_not_replace_default_archive(self):
        import transport.login as login_mod
        login_mod.KIRO_FLOW._pending = {**self._pending("login-container"), "profile": "work"}
        self.lc._read_auth_from_crew = lambda podman, container: "synthetic rows"
        resp = _run(login_mod._handle_login_get(_make_request()))
        self.assertEqual(_json_data(resp), {"status": "complete"})
        self.assertEqual(self._store.get("kiro", "work")["payload"], b"synthetic rows")
        self.assertEqual(self.written, [])

    def test_kiro_store_failure_can_retry_same_flow(self):
        import transport.login as login_mod
        flow = login_mod.KIRO_FLOW
        flow._pending = {**self._pending("login-container"), "profile": "work"}
        self.lc._read_auth_from_crew = lambda podman, container: "synthetic rows"
        with patch.object(self._store, "put", side_effect=OSError("write failed")):
            resp = _run(login_mod._handle_login_get(_make_request()))
        self.assertEqual(resp.status_code, 500)
        self.assertIsNotNone(flow.state)
        resp = _run(login_mod._handle_login_get(_make_request()))
        self.assertEqual(_json_data(resp), {"status": "complete"})
        self.assertEqual(self._store.get("kiro", "work")["payload"], b"synthetic rows")

    def test_named_kiro_completion_only_updates_matching_running_crews(self):
        import transport.login as login_mod
        login_mod.KIRO_FLOW._pending = {**self._pending("login-container"), "profile": "work"}
        self.lc._read_auth_from_crew = lambda podman, container: "synthetic rows"
        self.crews.update({
            "matching": {"status": "running", "container": "c-work", "acp_backend": "kiro", "acp_profile": "work"},
            "other": {"status": "running", "container": "c-other", "acp_backend": "kiro", "acp_profile": "personal"},
            "stopped": {"status": "stopped", "container": "c-stopped", "acp_backend": "kiro", "acp_profile": "work"},
        })
        resp = _run(login_mod._handle_login_get(_make_request()))
        self.assertEqual(_json_data(resp), {"status": "complete"})
        self.assertEqual(self.injected, ["c-work"])

    def test_codex_store_failure_can_retry_same_flow(self):
        import transport.login as login_mod
        flow = login_mod.CODEX_FLOW
        flow._pending = {**self._pending("login-container"), "profile": "work"}
        with patch.object(flow, "poll", return_value=b"synthetic archive"):
            with patch.object(self._store, "put", side_effect=OSError("write failed")):
                resp = _run(login_mod._handle_codex_login_get(_make_request()))
            self.assertEqual(resp.status_code, 500)
            self.assertIsNotNone(flow.state)
            resp = _run(login_mod._handle_codex_login_get(_make_request()))
        self.assertEqual(_json_data(resp), {"status": "complete"})
        self.assertIsNone(flow.state)
        self.assertIsNotNone(self._store.get("codex", "work"))

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


# ── Task 2.10: TestProfileParam, TestProfilesRoute, TestProfileTargetedLogout ─


class TestProfileParam(_BaseRouteTest):
    """POST /login/{backend}/{method} with profile="corp" stores under corp profile."""

    def setUp(self) -> None:
        super().setUp()
        import transport.login as login_mod
        from transport.config import Config
        self._orig_cfg = login_mod.cfg
        login_mod.cfg = Config(ga_crew_agent="kiro,claude,codex")
        self._login = login_mod

    def tearDown(self) -> None:
        self._login.cfg = self._orig_cfg
        super().tearDown()

    def _audit(self):
        from unittest.mock import MagicMock
        m = MagicMock()
        m.audit_auth_event = lambda **kw: None
        return m

    def test_kiro_api_key_corp_profile_stored(self):
        from transport.login import _handle_login_kiro_api_key_post
        req = _make_request({"secret": "kiro-corp-key", "profile": "corp"})
        with patch("transport.login._security") as ms:
            ms.audit_auth_event = lambda **kw: None
            resp = _run(_handle_login_kiro_api_key_post(req))
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(self._store.get("kiro"))  # default not set
        self.assertIsNotNone(self._store.get("kiro", profile="corp"))
        self.assertEqual(self._store.get("kiro", profile="corp")["payload"], b"kiro-corp-key")

    def test_kiro_api_key_no_profile_defaults_to_default(self):
        from transport.login import _handle_login_kiro_api_key_post
        req = _make_request({"secret": "kiro-default-key"})
        with patch("transport.login._security") as ms:
            ms.audit_auth_event = lambda **kw: None
            resp = _run(_handle_login_kiro_api_key_post(req))
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(self._store.get("kiro"))

    def test_claude_api_key_corp_profile_stored(self):
        from transport.login import _handle_login_claude_api_key_post
        req = _make_request({"secret": "claude-corp-key", "profile": "corp"})
        with patch("transport.login._security") as ms:
            ms.audit_auth_event = lambda **kw: None
            resp = _run(_handle_login_claude_api_key_post(req))
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(self._store.get("claude", profile="corp"))

    def test_codex_api_key_corp_profile_stored(self):
        from transport.login import _handle_login_codex_api_key_post
        req = _make_request({"secret": "codex-corp-key", "profile": "corp"})
        with patch("transport.login._security") as ms:
            ms.audit_auth_event = lambda **kw: None
            resp = _run(_handle_login_codex_api_key_post(req))
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(self._store.get("codex", profile="corp"))

    def test_invalid_profile_name_returns_400(self):
        from transport.login import _handle_login_kiro_api_key_post
        req = _make_request({"secret": "kiro-key", "profile": "Bad-Profile"})
        resp = _run(_handle_login_kiro_api_key_post(req))
        self.assertEqual(resp.status_code, 400)

    def test_reserved_default_profile_returns_400(self):
        """Explicitly posting profile='default' is rejected — 'default' is reserved."""
        from transport.login import _handle_login_kiro_api_key_post
        req = _make_request({"secret": "kiro-key", "profile": "default"})
        resp = _run(_handle_login_kiro_api_key_post(req))
        self.assertEqual(resp.status_code, 400)


class TestProfilesRoute(_BaseRouteTest):
    """GET /login/{backend}/profiles returns sorted profile list."""

    def setUp(self) -> None:
        super().setUp()
        import transport.login as login_mod
        from transport.config import Config
        self._orig_cfg = login_mod.cfg
        login_mod.cfg = Config(ga_crew_agent="kiro,claude,codex")
        self._login = login_mod

    def tearDown(self) -> None:
        self._login.cfg = self._orig_cfg
        super().tearDown()

    def test_kiro_profiles_empty(self):
        from transport.login import _handle_login_kiro_profiles_get
        resp = _run(_handle_login_kiro_profiles_get(_make_request()))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(_json_data(resp), {"profiles": []})

    def test_kiro_profiles_sorted(self):
        self._store.put("kiro", "api-key", "k1")
        self._store.put("kiro", "api-key", "k2", profile="corp")
        from transport.login import _handle_login_kiro_profiles_get
        resp = _run(_handle_login_kiro_profiles_get(_make_request()))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(_json_data(resp), {"profiles": ["corp", "default"]})

    def test_claude_profiles_empty(self):
        from transport.login import _handle_login_claude_profiles_get
        resp = _run(_handle_login_claude_profiles_get(_make_request()))
        self.assertEqual(_json_data(resp), {"profiles": []})

    def test_codex_profiles_empty(self):
        from transport.login import _handle_login_codex_profiles_get
        resp = _run(_handle_login_codex_profiles_get(_make_request()))
        self.assertEqual(_json_data(resp), {"profiles": []})


class TestProfileTargetedLogout(_LogoutHarness):
    """POST /logout/{backend}?profile=<p> targets only the specified profile."""

    def test_corp_logout_leaves_default_intact(self):
        """Logging out corp profile does not affect the default profile credential."""
        self._store.put("kiro", "api-key", "kiro-default-key")
        self._store.put("kiro", "api-key", "kiro-corp-key", profile="corp")
        import transport.login as login_mod
        handler = getattr(login_mod, self.ROUTES["kiro"])
        resp = _run(handler(_make_request(query_params={"profile": "corp"})))
        self.assertEqual(resp.status_code, 200)
        # Default profile still exists.
        self.assertIsNotNone(self._store.get("kiro"))
        # Corp profile is removed.
        self.assertIsNone(self._store.get("kiro", profile="corp"))

    def test_invalid_profile_name_returns_400(self):
        import transport.login as login_mod
        handler = getattr(login_mod, self.ROUTES["kiro"])
        resp = _run(handler(_make_request(query_params={"profile": "Bad-Profile"})))
        self.assertEqual(resp.status_code, 400)


# ── Task 2.11: in-flight flow is not aborted by a different-profile logout ────


class TestFlowNotAbortedByDifferentProfileLogout(_LogoutHarness):
    """An in-flight kiro default flow is NOT aborted by a corp logout."""

    def test_default_flow_survives_corp_logout(self):
        import transport.login as login_mod
        import time
        # Start a kiro flow for the default profile.
        login_mod.KIRO_FLOW._pending = {
            "container": None,
            "state": "starting",
            "started_at": time.time(),
            "profile": "default",
        }
        self.addCleanup(setattr, login_mod.KIRO_FLOW, "_pending", None)

        # Logout targeting "corp" profile — should NOT abort the default flow.
        handler = getattr(login_mod, self.ROUTES["kiro"])
        resp = _run(handler(_make_request(query_params={"profile": "corp"})))
        self.assertEqual(resp.status_code, 200)

        # The default flow's pending dict is still intact.
        self.assertIsNotNone(login_mod.KIRO_FLOW._pending)
        self.assertEqual(login_mod.KIRO_FLOW._pending.get("profile"), "default")
        # The corp abort was NOT called (abort_calls is empty for kiro).
        self.assertNotIn("kiro", self.abort_calls)

    def test_no_error_when_corp_cred_absent(self):
        """Logging out a non-existent corp profile returns 200, no error."""
        import transport.login as login_mod
        handler = getattr(login_mod, self.ROUTES["kiro"])
        resp = _run(handler(_make_request(query_params={"profile": "corp"})))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(_json_data(resp)["status"], "logged_out")
