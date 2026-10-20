"""Unit tests for the academy ghostship-spawn helper."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "academy" / "skills" / "ghostship-spawn" / "scripts" / "ghostship-spawn"


_loader = SourceFileLoader("ghostship_spawn_script", str(SCRIPT))
_spec = importlib.util.spec_from_loader("ghostship_spawn_script", _loader)
assert _spec is not None and _spec.loader is not None
spawn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(spawn)


class _Handler(BaseHTTPRequestHandler):
    requests: list[dict] = []
    response_status = 200
    response_body = b'{"id":"task-1"}'
    response_headers: dict[str, str] = {}

    def _record(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.requests.append(
            {
                "method": self.command,
                "path": self.path,
                "headers": dict(self.headers),
                "body": body,
            }
        )
        self.send_response(self.response_status)
        self.send_header("Content-Type", "application/json")
        for name, value in self.response_headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(self.response_body)

    do_GET = _record
    do_POST = _record

    def log_message(self, _format: str, *_args: object) -> None:
        pass


class TestGhostshipSpawn(TestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        _Handler.requests = []
        _Handler.response_status = 200
        _Handler.response_body = b'{"id":"task-1"}'
        _Handler.response_headers = {}
        self.cookie = "cookie-secret-for-test"
        self.cookie_path = self._tmp_cookie_path()
        self.cookie_path.write_text(self.cookie, encoding="utf-8")
        self.base_patch = patch.object(
            spawn, "_BASE_URL", f"http://127.0.0.1:{self.server.server_port}"
        )
        self.cookie_patch = patch.object(spawn, "_COOKIE_PATH", self.cookie_path)
        self.base_patch.start()
        self.cookie_patch.start()

    def tearDown(self) -> None:
        self.cookie_patch.stop()
        self.base_patch.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.cookie_path.unlink(missing_ok=True)

    @staticmethod
    def _tmp_cookie_path() -> Path:
        import tempfile

        handle, name = tempfile.mkstemp(prefix="ghostship-spawn-cookie-")
        os.close(handle)
        return Path(name)

    def _run(self, argv: list[str], stdin: str = "") -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(sys, "stdin", io.StringIO(stdin)),
            patch.object(sys, "stdout", stdout),
            patch.object(sys, "stderr", stderr),
        ):
            rc = spawn.main(argv)
        return rc, stdout.getvalue(), stderr.getvalue()

    def test_dispatch_request(self) -> None:
        rc, output, error = self._run(["ghost"], "do the work\n")
        self.assertEqual(rc, 0, error)
        self.assertEqual(json.loads(output), {"id": "task-1"})
        request = _Handler.requests[0]
        self.assertEqual((request["method"], request["path"]), ("POST", "/api/spawn"))
        self.assertEqual(
            json.loads(request["body"]),
            {"task": "do the work\n", "agent": "ghost", "keep": True},
        )
        self.assertEqual(request["headers"]["Cookie"], f"mc_token_5476={self.cookie}")

    def test_gateway_redirect_is_not_followed(self) -> None:
        _Handler.response_status = 302
        _Handler.response_headers = {"Location": "/redirect"}
        rc, output, error = self._run(["ghost"], "task")
        self.assertEqual(rc, 1)
        self.assertEqual(output, "")
        self.assertIn("HTTP 302", error)
        self.assertEqual(len(_Handler.requests), 1)

    def test_invalid_cookie_is_rejected_without_echo(self) -> None:
        self.cookie_path.write_text("top-secret\r\nX-Leak: yes", encoding="utf-8")
        rc, output, error = self._run(["ghost"], "task")
        self.assertEqual(rc, 1)
        self.assertEqual(output, "")
        self.assertIn("invalid format", error)
        self.assertNotIn("top-secret", output + error)
        self.assertNotIn("X-Leak", output + error)
        self.assertEqual(_Handler.requests, [])

    def test_status_steer_and_continue_paths_and_bodies(self) -> None:
        cases = [
            (["--status", "abc_1"], "", "GET", "/api/spawn/abc_1", {}),
            (["--steer", "abc-1"], "redirect\n", "POST", "/api/spawn/abc-1/steer", {"message": "redirect\n"}),
            (["--continue", "abc-1"], "resume\n", "POST", "/api/spawn/abc-1/continue", {"task": "resume\n"}),
        ]
        for argv, stdin, method, path, expected_body in cases:
            with self.subTest(argv=argv):
                rc, _output, error = self._run(argv, stdin)
                self.assertEqual(rc, 0, error)
                request = _Handler.requests[-1]
                self.assertEqual((request["method"], request["path"]), (method, path))
                actual = json.loads(request["body"]) if request["body"] else {}
                self.assertEqual(actual, expected_body)

    def test_empty_task_is_rejected_without_a_request(self) -> None:
        rc, output, error = self._run(["ghost"], " \n")
        self.assertEqual(rc, 1)
        self.assertEqual(output, "")
        self.assertIn("empty", error)
        self.assertEqual(_Handler.requests, [])

    def test_invalid_persona_and_task_id_are_rejected(self) -> None:
        for argv in (["Ghost"], ["bad/persona"], ["--status", "bad/id"], ["--steer", ""]):
            with self.subTest(argv=argv):
                rc, _output, error = self._run(argv, "task")
                self.assertEqual(rc, 1)
                self.assertIn("ghostship-spawn:", error)
        self.assertEqual(_Handler.requests, [])

    def test_non_2xx_reports_status_and_body_without_cookie(self) -> None:
        _Handler.response_status = 403
        _Handler.response_body = (f"denied {self.cookie}").encode()
        rc, output, error = self._run(["ghost"], "task")
        self.assertEqual(rc, 1)
        self.assertEqual(output, "")
        self.assertIn("HTTP 403", error)
        self.assertIn("denied", error)
        self.assertNotIn(self.cookie, output + error)

    def test_environment_and_arguments_cannot_redirect_destination(self) -> None:
        with patch.dict(
            os.environ,
            {
                "GHOSTSHIP_SPAWN_URL": "http://example.invalid/elsewhere",
                "HTTP_PROXY": "http://example.invalid:9999",
                "NO_PROXY": "",
                "no_proxy": "",
                "KIROCREW_CORS_ORIGINS": "http://origin.example, http://second.example",
            },
            clear=False,
        ):
            rc, _output, error = self._run(["ghost"], "task")
        self.assertEqual(rc, 0, error)
        request = _Handler.requests[0]
        self.assertEqual(request["path"], "/api/spawn")
        self.assertEqual(request["headers"]["Origin"], "http://origin.example")
        self.assertEqual(self.server.server_port, int(request["headers"].get("Host", "").rsplit(":", 1)[-1]))

    def test_skill_contract_and_executable_mode(self) -> None:
        skill = (ROOT / "academy" / "skills" / "ghostship-spawn" / "SKILL.md").read_text()
        self.assertIn("name: ghostship-spawn", skill)
        self.assertIn("allowed-tools:", skill)
        self.assertIn("--status", skill)
        self.assertIn("--steer", skill)
        self.assertIn("--continue", skill)
        self.assertIn("keep briefs short", skill.lower())
        self.assertTrue(os.access(SCRIPT, os.X_OK))
