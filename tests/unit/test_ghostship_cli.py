"""Unit tests for ghostship CLI subcommands cmd_status, cmd_stop, cmd_setup.

Uses the same importlib-based loader as test_ghostship_auth.py.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch, call

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_GS_PATH = str(_REPO_ROOT / "ghostship")


def _load_ghostship():
    loader = importlib.machinery.SourceFileLoader("ghostship_cli", _GS_PATH)
    spec = importlib.util.spec_from_loader("ghostship_cli", loader)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gs = _load_ghostship()


# ---------------------------------------------------------------------------
# cmd_stop
# ---------------------------------------------------------------------------

class TestCmdStop(unittest.TestCase):
    """Tests for cmd_stop.

    cmd_stop now stops ga-transport + ga-portal, then the Podman machine
    (macOS) or dedicated service (Linux). subprocess.run is mocked with a
    dispatcher keyed on the command so each test controls only the calls it
    cares about and records the full call sequence.
    """

    def _dispatch(self, container_rc=0, container_stderr="",
                  inspect_rc=1, machine_rc=0, machine_stderr=""):
        """Build a subprocess.run side_effect that routes by argv.

        Returns (side_effect, calls) where ``calls`` accumulates every argv
        list subprocess.run was invoked with.
        """
        calls: list = []

        def _run(cmd, *a, **kw):
            calls.append(list(cmd))
            res = MagicMock()
            res.stdout = ""
            if "machine" in cmd and "stop" in cmd:
                res.returncode = machine_rc
                res.stderr = machine_stderr
            elif cmd[:3] == ["systemctl", "--user", "stop"]:
                res.returncode = machine_rc
                res.stderr = machine_stderr
            elif "inspect" in cmd:
                res.returncode = inspect_rc
                res.stderr = ""
            else:  # container stop
                res.returncode = container_rc
                res.stderr = container_stderr
            return res

        return _run, calls

    def _run(self, side_effect, env=None, system="Darwin"):
        env = env or {}
        import os as _os
        with patch("shutil.which", return_value="/usr/bin/podman"), \
             patch("platform.system", return_value=system), \
             patch.dict(_os.environ, env, clear=False), \
             patch("subprocess.run", side_effect=side_effect), \
             patch("sys.stdout", new_callable=StringIO) as mock_out:
            code = gs.cmd_stop([])
            return code, mock_out.getvalue()

    # -- existing behaviour, updated for the new sequence -------------------

    def test_stop_success(self):
        side_effect, calls = self._dispatch(container_rc=0, machine_rc=0)
        code, out = self._run(side_effect, env={"GA_DEDICATED_MACHINE": "true"},
                              system="Darwin")
        self.assertEqual(code, 0)
        self.assertIn("stopped", out)

    def test_container_not_found_exits_zero(self):
        # container stop fails, inspect fails → truly not found; machine stop ok
        side_effect, calls = self._dispatch(
            container_rc=1,
            container_stderr="Error: no such container: ga-transport",
            inspect_rc=1,
            machine_rc=0,
        )
        code, out = self._run(side_effect, env={"GA_DEDICATED_MACHINE": "true"},
                              system="Darwin")
        self.assertEqual(code, 0)
        self.assertIn("not found", out)

    def test_podman_not_installed(self):
        import os as _os
        with patch("shutil.which", return_value=None), \
             patch("platform.system", return_value="Darwin"), \
             patch.dict(_os.environ, {"GA_DEDICATED_MACHINE": "false"}, clear=False), \
             patch("sys.stdout", new_callable=StringIO) as mock_out:
            code = gs.cmd_stop([])
        self.assertEqual(code, 0)
        self.assertIn("not found", mock_out.getvalue())

    def test_help_flag_exits_zero(self):
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            code = gs.cmd_stop(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("Usage", mock_out.getvalue())

    # -- task 2.1: macOS stops the machine ----------------------------------

    def test_macos_stops_machine(self):
        side_effect, calls = self._dispatch(container_rc=0, machine_rc=0)
        code, out = self._run(
            side_effect,
            env={"GA_DEDICATED_MACHINE": "true", "GA_MACHINE_NAME": "ghost-academy"},
            system="Darwin",
        )
        self.assertEqual(code, 0)
        # The machine stop must happen AFTER the container stop.
        machine_calls = [c for c in calls if "machine" in c and "stop" in c]
        self.assertTrue(machine_calls, "podman machine stop was never called")
        self.assertIn(["podman", "machine", "stop", "ghost-academy"], calls)
        container_idx = next(i for i, c in enumerate(calls) if "stop" in c and "ga-transport" in c)
        machine_idx = next(i for i, c in enumerate(calls) if "machine" in c and "stop" in c)
        self.assertLess(container_idx, machine_idx)

    # -- task 2.2: Linux dedicated stops the systemd service ----------------

    def test_linux_dedicated_stops_service(self):
        side_effect, calls = self._dispatch(container_rc=0, machine_rc=0)
        code, out = self._run(
            side_effect,
            env={"GA_DEDICATED_MACHINE": "true", "GA_MACHINE_NAME": "ghost-academy"},
            system="Linux",
        )
        self.assertEqual(code, 0)
        self.assertIn(
            ["systemctl", "--user", "stop", "podman-ghost-academy.service"],
            calls,
        )

    # -- task 2.3: already-stopped machine → exit 0 -------------------------

    def test_machine_already_stopped_exits_zero(self):
        # Container stop ok, but machine stop returns non-zero (already stopped).
        side_effect, calls = self._dispatch(
            container_rc=0,
            machine_rc=1,
            machine_stderr="Error: machine ghost-academy is not running",
        )
        code, out = self._run(
            side_effect,
            env={"GA_DEDICATED_MACHINE": "true", "GA_MACHINE_NAME": "ghost-academy"},
            system="Darwin",
        )
        self.assertEqual(code, 0)
        self.assertIn("already stopped or not found", out)


# ---------------------------------------------------------------------------
# cmd_status
# ---------------------------------------------------------------------------

class TestCmdStatus(unittest.TestCase):

    def _ports_json(self, port: str = "64057", ip: str = "127.0.0.1") -> str:
        return json.dumps({f"{port}/tcp": [{"HostIp": ip, "HostPort": port}]})

    def _run_inspect(self, stdout: str, returncode: int = 0) -> tuple[int, str]:
        result = MagicMock()
        result.returncode = returncode
        result.stdout = stdout
        with patch("shutil.which", return_value="/usr/bin/podman"), \
             patch("subprocess.run", return_value=result), \
             patch("sys.stdout", new_callable=StringIO) as mock_out:
            code = gs.cmd_status([])
            return code, mock_out.getvalue()

    def test_not_installed_when_podman_missing(self):
        with patch("shutil.which", return_value=None), \
             patch("sys.stdout", new_callable=StringIO) as mock_out:
            code = gs.cmd_status([])
        self.assertEqual(code, 0)
        self.assertIn("not installed", mock_out.getvalue())

    def test_not_installed_when_container_missing(self):
        code, out = self._run_inspect("", returncode=1)
        self.assertEqual(code, 0)
        self.assertIn("not installed", out)

    def test_stopped_state(self):
        stdout = f"exited\t2026-09-01T10:00:00.000000000Z\t{self._ports_json()}"
        code, out = self._run_inspect(stdout)
        self.assertEqual(code, 0)
        self.assertIn("stopped", out)

    def test_running_state_shows_port(self):
        # Use a recent timestamp so uptime calculation doesn't fail
        started = "2026-09-12T00:00:00.000000000Z"
        stdout = f"running\t{started}\t{self._ports_json('64057', '127.0.0.1')}"
        code, out = self._run_inspect(stdout)
        self.assertEqual(code, 0)
        self.assertIn("running", out)
        self.assertIn("64057", out)

    def test_nanosecond_timestamp_parsed(self):
        """Nanosecond timestamps (9 decimal places) must not crash."""
        started = "2026-09-12T10:30:00.123456789Z"
        stdout = f"running\t{started}\t{self._ports_json()}"
        code, out = self._run_inspect(stdout)
        self.assertEqual(code, 0)
        self.assertIn("running", out)

    def test_malformed_timestamp_does_not_crash(self):
        """Bad timestamp falls back gracefully."""
        stdout = f"running\tnot-a-timestamp\t{self._ports_json()}"
        code, out = self._run_inspect(stdout)
        self.assertEqual(code, 0)
        self.assertIn("running", out)

    def test_empty_ports_falls_back_to_env(self):
        started = "2026-09-12T10:00:00.000000000Z"
        stdout = f"running\t{started}\t{{}}"
        import os
        with patch.dict(os.environ, {"PORT": "12345"}):
            code, out = self._run_inspect(stdout)
        self.assertEqual(code, 0)
        self.assertIn("12345", out)


# ---------------------------------------------------------------------------
# cmd_setup
# ---------------------------------------------------------------------------

class TestCmdSetup(unittest.TestCase):

    def test_help_flag_exits_zero(self):
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            code = gs.cmd_setup(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("Usage", mock_out.getvalue())

    def test_delegates_to_exec_script(self):
        """cmd_setup must call _exec_script with the setup script."""
        with patch.object(gs, "_exec_script") as mock_exec:
            mock_exec.return_value = None
            gs.cmd_setup(["--agent", "kiro"])
        mock_exec.assert_called_once()
        args = mock_exec.call_args[0]
        self.assertIn("setup", args[0])

    def test_forwards_agent_flag(self):
        with patch.object(gs, "_exec_script") as mock_exec:
            mock_exec.return_value = None
            gs.cmd_setup(["--agent", "claude", "--url", "http://x.y/mcp"])
        _, forwarded = mock_exec.call_args[0]
        self.assertIn("--agent", forwarded)
        self.assertIn("claude", forwarded)
        self.assertIn("--url", forwarded)


if __name__ == "__main__":
    unittest.main()
