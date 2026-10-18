"""Unit tests for the ghostship CLI subcommands (TRN-255).

Covers:
- Task 1.2: cmd_upgrade --skills (install success → setup called; install failure
  → setup not called; no --skills → unchanged path)
- Task 2.2: cmd_skills (--help, no-agent, --agent forwarding)
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import pathlib
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, call, patch

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load_ghostship():
    """Import the ghostship CLI module dynamically."""
    gs_path = _REPO_ROOT / "ghostship"
    loader = importlib.machinery.SourceFileLoader("ghostship_cli_trn255", str(gs_path))
    spec = importlib.util.spec_from_loader("ghostship_cli_trn255", loader, origin=str(gs_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gs = _load_ghostship()


# ── cmd_upgrade --skills ─────────────────────────────────────────────────────

class TestCmdUpgradeSkills(unittest.TestCase):
    """ghostship upgrade --skills: subprocess install then cmd_setup."""

    def _mock_install_script(self, returncode: int):
        """Return a mock install.sh path that exists."""
        mock_path = MagicMock(spec=pathlib.Path)
        mock_path.exists.return_value = True
        mock_path.__str__ = lambda self: "/fake/scripts/install.sh"
        return mock_path

    def test_skills_flag_runs_install_then_setup_on_success(self):
        """install exits 0 → cmd_setup called."""
        with patch.object(gs, "_ghostship_dir") as mock_dir, \
             patch.object(gs, "subprocess") as mock_subprocess, \
             patch.object(gs, "cmd_setup", return_value=0) as mock_setup:
            fake_dir = MagicMock(spec=pathlib.Path)
            install_script = MagicMock(spec=pathlib.Path)
            install_script.exists.return_value = True
            install_script.__str__ = lambda self: "/fake/scripts/install.sh"
            fake_dir.__truediv__ = lambda self, other: install_script
            mock_dir.return_value = fake_dir
            mock_subprocess.run.return_value = MagicMock(returncode=0)

            rc = gs.cmd_upgrade(["--skills"])

        mock_setup.assert_called_once_with([])
        self.assertEqual(rc, 0)

    def test_skills_flag_skips_setup_when_install_fails(self):
        """install exits non-zero → cmd_setup NOT called."""
        with patch.object(gs, "_ghostship_dir") as mock_dir, \
             patch.object(gs, "subprocess") as mock_subprocess, \
             patch.object(gs, "cmd_setup", return_value=0) as mock_setup:
            fake_dir = MagicMock(spec=pathlib.Path)
            install_script = MagicMock(spec=pathlib.Path)
            install_script.exists.return_value = True
            install_script.__str__ = lambda self: "/fake/scripts/install.sh"
            fake_dir.__truediv__ = lambda self, other: install_script
            mock_dir.return_value = fake_dir
            mock_subprocess.run.return_value = MagicMock(returncode=1)

            rc = gs.cmd_upgrade(["--skills"])

        mock_setup.assert_not_called()
        self.assertEqual(rc, 1)

    def test_skills_flag_stripped_from_install_args(self):
        """--skills is not forwarded to install.sh."""
        with patch.object(gs, "_ghostship_dir") as mock_dir, \
             patch.object(gs, "subprocess") as mock_subprocess, \
             patch.object(gs, "cmd_setup", return_value=0):
            fake_dir = MagicMock(spec=pathlib.Path)
            install_script = MagicMock(spec=pathlib.Path)
            install_script.exists.return_value = True
            install_script.__str__ = lambda self: "/fake/scripts/install.sh"
            fake_dir.__truediv__ = lambda self, other: install_script
            mock_dir.return_value = fake_dir
            mock_subprocess.run.return_value = MagicMock(returncode=0)

            gs.cmd_upgrade(["--skills", "--port", "9999"])

        called_args = mock_subprocess.run.call_args[0][0]
        self.assertNotIn("--skills", called_args)
        self.assertIn("--port", called_args)
        self.assertIn("9999", called_args)

    def test_no_skills_flag_uses_exec_script(self):
        """Without --skills, _exec_script is called (original behaviour)."""
        with patch.object(gs, "_exec_script") as mock_exec:
            try:
                gs.cmd_upgrade(["--port", "9999"])
            except SystemExit:
                pass  # execvp would replace the process; mock raises nothing
        mock_exec.assert_called_once_with("scripts/install.sh", ["--port", "9999"])

    def test_help_flag_exits_0(self):
        out = io.StringIO()
        with patch("sys.stdout", out):
            rc = gs.cmd_upgrade(["--help"])
        self.assertEqual(rc, 0)
        self.assertIn("--skills", out.getvalue())

    def test_help_short_flag_exits_0(self):
        out = io.StringIO()
        with patch("sys.stdout", out):
            rc = gs.cmd_upgrade(["-h"])
        self.assertEqual(rc, 0)


# ── cmd_skills ───────────────────────────────────────────────────────────────

class TestCmdSkills(unittest.TestCase):
    """ghostship skills: alias for ghostship setup."""

    def test_help_flag_exits_0_and_mentions_setup(self):
        out = io.StringIO()
        with patch("sys.stdout", out):
            rc = gs.cmd_skills(["--help"])
        self.assertEqual(rc, 0)
        text = out.getvalue()
        self.assertIn("setup", text)
        self.assertIn("ghostship setup", text)

    def test_help_short_flag(self):
        out = io.StringIO()
        with patch("sys.stdout", out):
            rc = gs.cmd_skills(["-h"])
        self.assertEqual(rc, 0)

    def test_delegates_to_cmd_setup_with_same_args(self):
        """ghostship skills [args] delegates to cmd_setup([args])."""
        with patch.object(gs, "cmd_setup", return_value=0) as mock_setup:
            rc = gs.cmd_skills(["--agent", "kiro"])
        mock_setup.assert_called_once_with(["--agent", "kiro"])
        self.assertEqual(rc, 0)

    def test_no_args_delegates_to_cmd_setup(self):
        with patch.object(gs, "cmd_setup", return_value=0) as mock_setup:
            rc = gs.cmd_skills([])
        mock_setup.assert_called_once_with([])
        self.assertEqual(rc, 0)

    def test_forwards_exit_code_from_setup(self):
        with patch.object(gs, "cmd_setup", return_value=42):
            rc = gs.cmd_skills([])
        self.assertEqual(rc, 42)

    def test_skills_in_dispatch_table(self):
        """'skills' must be a registered command in _COMMANDS."""
        self.assertIn("skills", gs._COMMANDS)
        self.assertIs(gs._COMMANDS["skills"], gs.cmd_skills)

    def test_skills_in_usage_string(self):
        """_USAGE must mention the skills subcommand."""
        self.assertIn("skills", gs._USAGE)


if __name__ == "__main__":
    unittest.main()
