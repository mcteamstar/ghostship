"""Unit tests for the ghostship CLI auth subcommand group (trn-150).

Covers _resolve_transport_url, _parse_api_key, _http_json, auth_login,
auth_logout, and cmd_auth using stdlib-only mocking (no external deps).
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import json
import os
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, call, patch

# ---------------------------------------------------------------------------
# Load the ghostship script as a module (it has no .py extension)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_GS_PATH = str(_REPO_ROOT / "ghostship")


def _load_ghostship():
    loader = importlib.machinery.SourceFileLoader("ghostship", _GS_PATH)
    spec = importlib.util.spec_from_loader("ghostship", loader)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gs = _load_ghostship()


# ---------------------------------------------------------------------------
# _resolve_transport_url
# ---------------------------------------------------------------------------


class TestResolveTransportUrl(unittest.TestCase):
    def test_explicit_url_flag_returned(self):
        result = gs._resolve_transport_url(["--url", "http://example.com/"])
        self.assertEqual(result, "http://example.com")

    def test_trailing_slash_stripped(self):
        self.assertEqual(
            gs._resolve_transport_url(["--url", "http://a.b.c/"]),
            "http://a.b.c",
        )

    def test_url_flag_without_value_falls_back_to_env(self):
        # --url at the end of the list with no following token
        with patch.dict(os.environ, {"GHOSTSHIP_URL": "http://env-host:9000"}):
            result = gs._resolve_transport_url(["--url"])
        self.assertEqual(result, "http://env-host:9000")

    def test_env_var_used_when_no_flag(self):
        with patch.dict(os.environ, {"GHOSTSHIP_URL": "http://my-host:64057"}, clear=False):
            result = gs._resolve_transport_url([])
        self.assertEqual(result, "http://my-host:64057")

    def test_default_localhost_when_no_flag_no_env(self):
        env = {k: v for k, v in os.environ.items() if k != "GHOSTSHIP_URL"}
        with patch.dict(os.environ, env, clear=True):
            result = gs._resolve_transport_url([])
        self.assertEqual(result, "http://localhost:64057")

    def test_url_flag_takes_priority_over_env(self):
        with patch.dict(os.environ, {"GHOSTSHIP_URL": "http://env-host:9000"}):
            result = gs._resolve_transport_url(["--url", "http://flag-host:1234"])
        self.assertEqual(result, "http://flag-host:1234")

    def test_other_flags_ignored(self):
        result = gs._resolve_transport_url(["--api-key", "tok", "--url", "http://x.y"])
        self.assertEqual(result, "http://x.y")


# ---------------------------------------------------------------------------
# _parse_api_key
# ---------------------------------------------------------------------------


class TestParseApiKey(unittest.TestCase):
    def test_api_key_returned(self):
        self.assertEqual(gs._parse_api_key(["--api-key", "tok123"]), "tok123")

    def test_none_when_absent(self):
        self.assertIsNone(gs._parse_api_key([]))

    def test_none_when_flag_at_end(self):
        # --api-key at the end with no following token
        self.assertIsNone(gs._parse_api_key(["--api-key"]))

    def test_ignores_unrelated_flags(self):
        self.assertIsNone(gs._parse_api_key(["--url", "http://x"]))


# ---------------------------------------------------------------------------
# _http_json
# ---------------------------------------------------------------------------


def _make_http_response(body: bytes, status: int = 200):
    """Return a minimal urllib response-like mock."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


class TestHttpJson(unittest.TestCase):
    def test_get_returns_parsed_json(self):
        payload = json.dumps({"status": "pending"}).encode()
        mock_resp = _make_http_response(payload)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = gs._http_json("http://host/login", "GET")
        self.assertEqual(result, {"status": "pending"})

    def test_post_with_body_sets_content_type(self):
        payload = json.dumps({"status": "pending"}).encode()
        mock_resp = _make_http_response(payload)
        captured = {}

        def fake_urlopen(req):
            captured["req"] = req
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            gs._http_json("http://host/login", "POST", body={"foo": "bar"})

        self.assertEqual(captured["req"].get_header("Content-type"), "application/json")

    def test_api_key_sets_authorization_header(self):
        payload = b"{}"
        mock_resp = _make_http_response(payload)
        captured = {}

        def fake_urlopen(req):
            captured["req"] = req
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            gs._http_json("http://host/login", "GET", api_key="secret")

        self.assertEqual(captured["req"].get_header("Authorization"), "Bearer secret")

    def test_empty_body_returns_empty_dict(self):
        mock_resp = _make_http_response(b"")
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = gs._http_json("http://host/login", "GET")
        self.assertEqual(result, {})

    def test_http_error_propagates(self):
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(
                "http://host/login", 409, "Conflict", {}, io.BytesIO(b"Already authenticated.")
            ),
        ):
            with self.assertRaises(urllib.error.HTTPError):
                gs._http_json("http://host/login", "POST", body={})

    def test_url_error_propagates(self):
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("Connection refused"),
        ):
            with self.assertRaises(urllib.error.URLError):
                gs._http_json("http://host/login", "GET")


# ---------------------------------------------------------------------------
# auth_login
# ---------------------------------------------------------------------------


class TestAuthLogin(unittest.TestCase):
    def _run(self, args, http_responses, env=None):
        """Run auth_login with a sequence of fake HTTP responses."""
        call_idx = [0]
        responses = list(http_responses)

        def fake_http_json(url, method, body=None, api_key=None):
            if call_idx[0] >= len(responses):
                raise AssertionError(f"Unexpected HTTP call #{call_idx[0]}")
            resp = responses[call_idx[0]]
            call_idx[0] += 1
            if isinstance(resp, Exception):
                raise resp
            return resp

        patch_env = patch.dict(os.environ, env or {}, clear=False)
        patch_http = patch.object(gs, "_http_json", side_effect=fake_http_json)
        patch_sleep = patch("time.sleep")

        with patch_env, patch_http, patch_sleep:
            return gs.auth_login(args)

    def test_success_after_one_poll(self):
        rc = self._run(
            ["--url", "http://host:64057"],
            [
                {"status": "pending", "login_url": "https://auth.example.com/activate", "code": "ABC123"},
                {"status": "complete"},
            ],
        )
        self.assertEqual(rc, 0)

    def test_already_authenticated_via_status_complete(self):
        rc = self._run([], [{"status": "complete"}])
        self.assertEqual(rc, 0)

    def test_already_authenticated_via_already_authenticated_field(self):
        rc = self._run([], [{"already_authenticated": True}])
        self.assertEqual(rc, 0)

    def test_connection_error_on_post_returns_nonzero(self):
        rc = self._run(
            [],
            [urllib.error.URLError("Connection refused")],
        )
        self.assertEqual(rc, 1)

    def test_http_error_409_on_post_returns_nonzero(self):
        """409 'already authenticated' must not show 'could not reach transport'."""
        http_err = urllib.error.HTTPError(
            "http://host/login", 409, "Conflict", {},
            io.BytesIO(b"Already authenticated. POST /logout first.")
        )
        rc = self._run([], [http_err])
        self.assertEqual(rc, 1)

    def test_http_error_409_prints_server_message_not_connection_error(self, capsys=None):
        """Error output for 409 should mention HTTP code, not 'could not reach'."""
        http_err = urllib.error.HTTPError(
            "http://host/login", 409, "Conflict", {},
            io.BytesIO(b"Already authenticated. POST /logout first.")
        )

        captured_stderr = io.StringIO()
        with patch("sys.stderr", captured_stderr):
            rc = self._run([], [http_err])

        err_out = captured_stderr.getvalue()
        self.assertEqual(rc, 1)
        self.assertIn("409", err_out)
        # Must NOT claim the transport is unreachable
        self.assertNotIn("could not reach", err_out)

    def test_http_error_during_poll_returns_nonzero(self):
        http_err = urllib.error.HTTPError(
            "http://host/login", 404, "Not Found", {},
            io.BytesIO(b"No login in progress.")
        )
        rc = self._run(
            [],
            [
                {"status": "pending", "login_url": "https://auth/activate", "code": "X"},
                http_err,
            ],
        )
        self.assertEqual(rc, 1)

    def test_http_error_during_poll_does_not_say_lost_connection(self):
        http_err = urllib.error.HTTPError(
            "http://host/login", 404, "Not Found", {},
            io.BytesIO(b"No login in progress.")
        )
        captured_stderr = io.StringIO()
        with patch("sys.stderr", captured_stderr):
            rc = self._run(
                [],
                [
                    {"status": "pending", "login_url": "https://auth/activate", "code": "X"},
                    http_err,
                ],
            )
        err_out = captured_stderr.getvalue()
        self.assertEqual(rc, 1)
        self.assertIn("404", err_out)
        self.assertNotIn("lost connection", err_out)

    def test_connection_error_during_poll_returns_nonzero(self):
        rc = self._run(
            [],
            [
                {"status": "pending", "login_url": "https://auth/activate", "code": "X"},
                urllib.error.URLError("Connection refused"),
            ],
        )
        self.assertEqual(rc, 1)

    def test_timeout_returns_nonzero(self):
        """If all polls return 'pending', the client-side timeout fires."""
        # Build enough 'pending' responses to exceed _AUTH_TIMEOUT
        n_polls = (gs._AUTH_TIMEOUT // gs._AUTH_POLL_INTERVAL) + 2
        responses = [
            {"status": "pending", "login_url": "https://auth/activate", "code": "X"},
        ] + [{"status": "pending"}] * n_polls

        rc = self._run([], responses)
        self.assertEqual(rc, 1)

    def test_timeout_message_includes_retry_url(self):
        n_polls = (gs._AUTH_TIMEOUT // gs._AUTH_POLL_INTERVAL) + 2
        responses = [
            {"status": "pending", "login_url": "https://auth/activate", "code": "X"},
        ] + [{"status": "pending"}] * n_polls

        captured_stderr = io.StringIO()
        with patch("sys.stderr", captured_stderr):
            self._run([], responses)

        self.assertIn("https://auth/activate", captured_stderr.getvalue())

    def test_api_key_forwarded(self):
        """--api-key is passed through to HTTP calls."""
        calls = []

        def fake_http(url, method, body=None, api_key=None):
            calls.append(api_key)
            if len(calls) == 1:
                return {"status": "pending", "login_url": "http://a", "code": "Y"}
            return {"status": "complete"}

        with patch.object(gs, "_http_json", side_effect=fake_http), patch("time.sleep"):
            gs.auth_login(["--api-key", "mytoken"])

        self.assertTrue(all(k == "mytoken" for k in calls))

    def test_custom_url_used(self):
        """--url is forwarded to all HTTP calls."""
        seen_urls = []

        def fake_http(url, method, body=None, api_key=None):
            seen_urls.append(url)
            if len(seen_urls) == 1:
                return {"status": "pending", "login_url": "http://a", "code": "Z"}
            return {"status": "complete"}

        with patch.object(gs, "_http_json", side_effect=fake_http), patch("time.sleep"):
            gs.auth_login(["--url", "http://remote:9999"])

        for u in seen_urls:
            self.assertTrue(u.startswith("http://remote:9999"), u)


# ---------------------------------------------------------------------------
# auth_logout
# ---------------------------------------------------------------------------


class TestAuthLogout(unittest.TestCase):
    def test_success(self):
        with patch.object(gs, "_http_json", return_value={}):
            rc = gs.auth_logout([])
        self.assertEqual(rc, 0)

    def test_connection_error_returns_nonzero(self):
        with patch.object(
            gs, "_http_json", side_effect=urllib.error.URLError("Connection refused")
        ):
            rc = gs.auth_logout([])
        self.assertEqual(rc, 1)

    def test_http_error_404_returns_nonzero(self):
        """404 'Not authenticated' must produce a clear error, not 'could not reach'."""
        http_err = urllib.error.HTTPError(
            "http://host/logout", 404, "Not Found", {},
            io.BytesIO(b"Not authenticated.")
        )
        captured_stderr = io.StringIO()
        with patch.object(gs, "_http_json", side_effect=http_err), \
             patch("sys.stderr", captured_stderr):
            rc = gs.auth_logout([])
        self.assertEqual(rc, 1)
        err = captured_stderr.getvalue()
        self.assertIn("404", err)
        self.assertNotIn("could not reach", err)

    def test_api_key_forwarded(self):
        calls = []

        def fake_http(url, method, body=None, api_key=None):
            calls.append(api_key)
            return {}

        with patch.object(gs, "_http_json", side_effect=fake_http):
            gs.auth_logout(["--api-key", "secret"])

        self.assertEqual(calls, ["secret"])

    def test_custom_url_used(self):
        calls = []

        def fake_http(url, method, body=None, api_key=None):
            calls.append(url)
            return {}

        with patch.object(gs, "_http_json", side_effect=fake_http):
            gs.auth_logout(["--url", "http://remote:9999"])

        self.assertEqual(calls, ["http://remote:9999/logout"])


# ---------------------------------------------------------------------------
# cmd_auth dispatcher
# ---------------------------------------------------------------------------


class TestCmdAuth(unittest.TestCase):
    def test_no_args_prints_usage_and_exits_zero(self):
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            rc = gs.cmd_auth([])
        self.assertEqual(rc, 0)
        self.assertIn("login", captured.getvalue())
        self.assertIn("logout", captured.getvalue())

    def test_help_flag_prints_usage_and_exits_zero(self):
        for flag in ("--help", "-h"):
            with self.subTest(flag=flag):
                captured = io.StringIO()
                with patch("sys.stdout", captured):
                    rc = gs.cmd_auth([flag])
                self.assertEqual(rc, 0)
                self.assertIn("login", captured.getvalue())

    def test_unknown_subcommand_returns_nonzero(self):
        captured_err = io.StringIO()
        with patch("sys.stderr", captured_err):
            rc = gs.cmd_auth(["bogus"])
        self.assertEqual(rc, 1)
        self.assertIn("bogus", captured_err.getvalue())

    def test_login_subcommand_dispatches(self):
        mock_login = MagicMock(return_value=0)
        orig = gs._AUTH_COMMANDS.copy()
        try:
            gs._AUTH_COMMANDS["login"] = mock_login
            rc = gs.cmd_auth(["login", "--url", "http://x"])
        finally:
            gs._AUTH_COMMANDS.update(orig)
        mock_login.assert_called_once_with(["--url", "http://x"])
        self.assertEqual(rc, 0)

    def test_logout_subcommand_dispatches(self):
        mock_logout = MagicMock(return_value=0)
        orig = gs._AUTH_COMMANDS.copy()
        try:
            gs._AUTH_COMMANDS["logout"] = mock_logout
            rc = gs.cmd_auth(["logout"])
        finally:
            gs._AUTH_COMMANDS.update(orig)
        mock_logout.assert_called_once_with([])
        self.assertEqual(rc, 0)

    def test_auth_registered_in_top_level_commands(self):
        self.assertIn("auth", gs._COMMANDS)
        self.assertIs(gs._COMMANDS["auth"], gs.cmd_auth)


if __name__ == "__main__":
    unittest.main()
