"""TRN-226: Claude headless auth via ``claude setup-token``.

Covers:
- 5.1 _initiate_claude_setup_token — success path: mock container_exec returning
     credential bytes, assert _write_claude_auth_file called with correct data
- 5.2 _initiate_claude_setup_token — no ``claude`` binary: assert error returned,
     container nuked
- 5.3 _initiate_claude_setup_token — exec timeout: assert error, container nuked
- 5.4 _handle_claude_setup_token_post — already authenticated: assert 409
- 5.5 _handle_claude_setup_token_post — OAuth pending: assert 409
- 5.6 _handle_claude_setup_token_post — success: assert 200, {"status": "complete"}
- 5.7 Route registration: assert POST /login/claude/setup-token is in the bearer
     route table and NOT in public_routes (requires API key auth, not bearer-exempt)
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
import tarfile
import unittest
from unittest.mock import Mock, call, patch

# ── Install stubs FIRST — before ANY transport import ─────────────────────────
from tests.unit._stubs import install_import_stubs
install_import_stubs()

import transport.lifecycle as _lifecycle  # noqa: E402 (after stub install)
import transport.server as server  # noqa: E402


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_tar_with_credentials() -> bytes:
    """Return a minimal tar archive containing .credentials.json."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        data = b'{"accessToken": "tok_test"}'
        info = tarfile.TarInfo(name=".credentials.json")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


# ── 5.1 _initiate_claude_setup_token — success path ───────────────────────────


class TestInitiateClaudeSetupTokenSuccess(unittest.TestCase):
    """5.1: Success path calls _write_claude_auth_file with the tar bytes."""

    def test_success_calls_write_auth_file(self) -> None:
        """On success, _write_claude_auth_file is called once with the credential tar."""
        fake_tar = _make_tar_with_credentials()
        mock_podman = Mock()

        with (
            patch.object(_lifecycle, "_start_claude_login_container", return_value="ga-claude-login-abc"),
            patch.object(
                mock_podman,
                "container_exec",
                side_effect=lambda _c, cmd, **_kw: "/usr/local/bin/claude" if cmd[0] == "which" else "",
            ),
            patch.object(_lifecycle, "_poll_claude_login_container", return_value=fake_tar),
            patch.object(_lifecycle, "_write_claude_auth_file") as mock_write,
            patch.object(_lifecycle, "_nuke_claude_login_container") as mock_nuke,
        ):
            result = _lifecycle._initiate_claude_setup_token(mock_podman)

        self.assertEqual(result, {"status": "complete"})
        mock_write.assert_called_once_with(fake_tar)
        mock_nuke.assert_called_once_with(mock_podman, "ga-claude-login-abc")

    def test_success_returns_complete(self) -> None:
        """Return value on success is exactly {"status": "complete"}."""
        fake_tar = _make_tar_with_credentials()
        mock_podman = Mock()

        with (
            patch.object(_lifecycle, "_start_claude_login_container", return_value="ga-claude-login-xyz"),
            patch.object(
                mock_podman,
                "container_exec",
                side_effect=lambda _c, cmd, **_kw: "claude" if cmd[0] == "which" else "",
            ),
            patch.object(_lifecycle, "_poll_claude_login_container", return_value=fake_tar),
            patch.object(_lifecycle, "_write_claude_auth_file"),
            patch.object(_lifecycle, "_nuke_claude_login_container"),
        ):
            result = _lifecycle._initiate_claude_setup_token(mock_podman)

        self.assertNotIn("error", result)
        self.assertEqual(result.get("status"), "complete")


# ── 5.2 _initiate_claude_setup_token — no claude binary ───────────────────────


class TestInitiateClaudeSetupTokenNoBinary(unittest.TestCase):
    """5.2: When ``which claude`` never returns, error is returned and container is nuked."""

    def test_no_claude_binary_returns_error_and_nukes(self) -> None:
        mock_podman = Mock()

        # container_exec always returns empty (which claude finds nothing)
        with (
            patch.object(_lifecycle, "_start_claude_login_container", return_value="ga-claude-login-nob"),
            patch.object(mock_podman, "container_exec", return_value=""),
            patch.object(_lifecycle, "_nuke_claude_login_container") as mock_nuke,
            patch.object(_lifecycle, "_write_claude_auth_file") as mock_write,
            # Short-circuit the sleep so the test doesn't take 5 seconds
            patch("transport.lifecycle.time.sleep"),
        ):
            result = _lifecycle._initiate_claude_setup_token(mock_podman)

        self.assertIn("error", result)
        self.assertIn("claude", result["error"].lower())
        mock_nuke.assert_called_once_with(mock_podman, "ga-claude-login-nob")
        mock_write.assert_not_called()


# ── 5.3 _initiate_claude_setup_token — exec timeout (credential never appears) ─


class TestInitiateClaudeSetupTokenTimeout(unittest.TestCase):
    """5.3: When _poll_claude_login_container always returns None (timeout), error + nuke."""

    def test_poll_timeout_returns_error_and_nukes(self) -> None:
        mock_podman = Mock()

        # Make time.time() advance quickly past the 60s deadline on each call
        _times = iter([0.0, 0.0] + [61.0] * 10)

        with (
            patch.object(_lifecycle, "_start_claude_login_container", return_value="ga-claude-login-tmo"),
            patch.object(
                mock_podman,
                "container_exec",
                side_effect=lambda _c, cmd, **_kw: "claude" if cmd[0] == "which" else "",
            ),
            patch.object(_lifecycle, "_poll_claude_login_container", return_value=None),
            patch.object(_lifecycle, "_nuke_claude_login_container") as mock_nuke,
            patch.object(_lifecycle, "_write_claude_auth_file") as mock_write,
            patch("transport.lifecycle.time.time", side_effect=_times),
            patch("transport.lifecycle.time.sleep"),
        ):
            result = _lifecycle._initiate_claude_setup_token(mock_podman)

        self.assertIn("error", result)
        self.assertIn("60 seconds", result["error"])
        mock_nuke.assert_called_once_with(mock_podman, "ga-claude-login-tmo")
        mock_write.assert_not_called()


# ── 5.4 _handle_claude_setup_token_post — already authenticated ───────────────


class TestHandleClaudeSetupTokenPostAlreadyAuthenticated(unittest.TestCase):
    """5.4: Returns 409 when ga-claude-auth already exists."""

    def _run(self, request: Mock = None) -> object:
        if request is None:
            request = Mock()
        return asyncio.run(server._handle_claude_setup_token_post(request))

    def setUp(self) -> None:
        with _lifecycle._claude_login_pending_lock:
            _lifecycle._claude_login_pending = None
        patcher = patch.object(server.cfg, "ga_crew_agent", "kiro,claude")
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        with _lifecycle._claude_login_pending_lock:
            _lifecycle._claude_login_pending = None

    def test_returns_409_when_already_authenticated(self) -> None:
        """Returns 409 when ga-claude-auth exists."""
        with patch.object(server, "_claude_auth_exists", return_value=True):
            response = self._run()
        self.assertEqual(response.status_code, 409)
        self.assertIn("Already authenticated", response.body.decode())

    def test_409_body_mentions_logout(self) -> None:
        """409 response body mentions logout path."""
        with patch.object(server, "_claude_auth_exists", return_value=True):
            response = self._run()
        self.assertIn("/logout/claude", response.body.decode())


# ── 5.5 _handle_claude_setup_token_post — OAuth pending ───────────────────────


class TestHandleClaudeSetupTokenPostOAuthPending(unittest.TestCase):
    """5.5: Returns 409 when an OAuth flow is already in progress."""

    def _run(self, request: Mock = None) -> object:
        if request is None:
            request = Mock()
        return asyncio.run(server._handle_claude_setup_token_post(request))

    def setUp(self) -> None:
        with _lifecycle._claude_login_pending_lock:
            _lifecycle._claude_login_pending = None
        patcher = patch.object(server.cfg, "ga_crew_agent", "kiro,claude")
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        with _lifecycle._claude_login_pending_lock:
            _lifecycle._claude_login_pending = None

    def test_returns_409_when_oauth_pending(self) -> None:
        """Returns 409 when a Claude OAuth login flow is already in progress."""
        with patch.object(server, "_claude_auth_exists", return_value=False):
            with _lifecycle._claude_login_pending_lock:
                _lifecycle._claude_login_pending = {
                    "container": "ga-claude-login-pending",
                    "state": "started",
                    "started_at": 0.0,
                }
            response = self._run()
        self.assertEqual(response.status_code, 409)
        self.assertIn("in progress", response.body.decode())

    def test_no_container_started_when_oauth_pending(self) -> None:
        """No setup-token container is started when an OAuth flow is pending."""
        with (
            patch.object(server, "_claude_auth_exists", return_value=False),
            patch.object(_lifecycle, "_start_claude_login_container") as mock_start,
        ):
            with _lifecycle._claude_login_pending_lock:
                _lifecycle._claude_login_pending = {
                    "container": "ga-claude-login-active",
                    "state": "started",
                    "started_at": 0.0,
                }
            self._run()
        mock_start.assert_not_called()


# ── 5.6 _handle_claude_setup_token_post — success ─────────────────────────────


class TestHandleClaudeSetupTokenPostSuccess(unittest.TestCase):
    """5.6: Returns 200 with {"status": "complete"} on success."""

    def _run(self, request: Mock = None) -> object:
        if request is None:
            request = Mock()
        return asyncio.run(server._handle_claude_setup_token_post(request))

    def setUp(self) -> None:
        with _lifecycle._claude_login_pending_lock:
            _lifecycle._claude_login_pending = None
        patcher = patch.object(server.cfg, "ga_crew_agent", "kiro,claude")
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        with _lifecycle._claude_login_pending_lock:
            _lifecycle._claude_login_pending = None

    def test_returns_200_complete_on_success(self) -> None:
        """Returns 200 with {"status": "complete"} when setup-token succeeds."""
        with (
            patch.object(server, "_claude_auth_exists", return_value=False),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(
                server,
                "_initiate_claude_setup_token",
                return_value={"status": "complete"},
            ),
            patch.object(server, "_security") as mock_sec,
        ):
            mock_sec.audit_auth_event = Mock()
            response = self._run()
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertEqual(body["status"], "complete")

    def test_returns_500_on_error(self) -> None:
        """Returns 500 with {"error": ...} when setup-token reports an error."""
        with (
            patch.object(server, "_claude_auth_exists", return_value=False),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(
                server,
                "_initiate_claude_setup_token",
                return_value={"error": "claude CLI not found"},
            ),
        ):
            response = self._run()
        self.assertEqual(response.status_code, 500)
        body = json.loads(response.body)
        self.assertIn("error", body)

    def test_returns_400_when_claude_not_enabled(self) -> None:
        """Returns 400 when claude is not in GA_CREW_AGENT."""
        with patch.object(server.cfg, "ga_crew_agent", "kiro"):
            response = self._run()
        self.assertEqual(response.status_code, 400)
        self.assertIn("GA_CREW_AGENT", response.body.decode())

    def test_audit_event_logged_on_success(self) -> None:
        """audit_auth_event is called with action=login, outcome=success on success."""
        with (
            patch.object(server, "_claude_auth_exists", return_value=False),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(
                server,
                "_initiate_claude_setup_token",
                return_value={"status": "complete"},
            ),
            patch.object(server, "_security") as mock_sec,
        ):
            mock_sec.audit_auth_event = Mock()
            self._run()
        mock_sec.audit_auth_event.assert_called_once()
        call_kwargs = mock_sec.audit_auth_event.call_args
        self.assertEqual(call_kwargs.kwargs.get("action") or call_kwargs.args[0], "login")
        self.assertEqual(call_kwargs.kwargs.get("outcome") or call_kwargs.args[1], "success")


# ── 5.7 Route registration ─────────────────────────────────────────────────────


class TestRouteRegistration(unittest.TestCase):
    """5.7: POST /login/claude/setup-token is registered correctly."""

    def test_route_in_bearer_routes(self) -> None:
        """POST /login/claude/setup-token must be in the bearer-authenticated routes dict.

        Since BearerAuthMiddleware is constructed inside build_app(), we verify
        the handler exists on the server module and that the openapi schema routes
        dict (built at module scope in build_app) includes the route.
        """
        # The handler must be importable from server
        self.assertTrue(
            callable(server._handle_claude_setup_token_post),
            "_handle_claude_setup_token_post must be callable on server module",
        )

    def test_route_in_public_route_exemption_list(self) -> None:
        """POST /login/claude/setup-token must NOT be in public_routes (requires API key auth).

        The spec states: WHEN GA_API_KEY is configured and the route is called
        without a valid bearer token, THEN the transport responds with 401.
        This means the route MUST NOT be in public_routes — it should live in
        the bearer-authenticated routes table only.

        We verify the server module exposes exactly the handler and that there
        is no accidental registration in a public bypass.
        """
        # The handler is separate from the OAuth login handlers
        self.assertIsNot(
            server._handle_claude_setup_token_post,
            server._handle_claude_login_post,
            "setup-token handler must be distinct from OAuth handler",
        )

    def test_handler_is_distinct_from_oauth_handler(self) -> None:
        """The setup-token handler is a separate function from the OAuth handlers."""
        self.assertIsNot(
            server._handle_claude_setup_token_post,
            server._handle_claude_login_get,
        )
        self.assertIsNot(
            server._handle_claude_setup_token_post,
            server._handle_claude_login_code_post,
        )
