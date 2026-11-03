"""Unit tests for the ghostship CLI subcommands (TRN-255).

Covers:
- Task 1.2: cmd_upgrade --skills (install success → setup called; install failure
  → setup not called; no --skills → unchanged path)
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

    # Shared context manager stack used by all --skills tests.
    # Patches git helpers directly (like TestCmdUpgradeVersionDetection) so
    # subprocess.run only ever sees the install call, and uses a real Path for
    # _ghostship_dir so path-construction bugs are caught.
    def _skills_patches(self, install_rc: int = 0):
        return (
            patch.object(gs, "_ghostship_dir", return_value=pathlib.Path("/repo")),
            patch.object(gs, "_git_current_tag", return_value=None),
            patch.object(gs, "_git_is_dirty", return_value=False),
            patch.object(pathlib.Path, "exists", return_value=True),
            patch.object(gs.subprocess, "run",
                         return_value=MagicMock(returncode=install_rc,
                                                stdout="", stderr="")),
        )

    def test_skills_flag_runs_install_then_setup_on_success(self):
        """install exits 0 → cmd_setup called; install script is bin/install.sh."""
        with patch.object(gs, "_ghostship_dir", return_value=pathlib.Path("/repo")), \
             patch.object(gs, "_git_current_tag", return_value=None), \
             patch.object(gs, "_git_is_dirty", return_value=False), \
             patch.object(gs, "cmd_setup", return_value=0) as mock_setup, \
             patch.object(pathlib.Path, "exists", return_value=True), \
             patch.object(gs.subprocess, "run",
                          return_value=MagicMock(returncode=0)) as mock_run:
            rc = gs.cmd_upgrade(["--skills"])

        mock_setup.assert_called_once_with([])
        self.assertEqual(rc, 0)
        # Verify the subprocess was invoked with bin/install.sh, not scripts/install.sh
        install_cmd = mock_run.call_args[0][0]
        self.assertIn("bin/install.sh", str(install_cmd[0]))

    def test_skills_flag_skips_setup_when_install_fails(self):
        """install exits non-zero → cmd_setup NOT called."""
        with patch.object(gs, "_ghostship_dir", return_value=pathlib.Path("/repo")), \
             patch.object(gs, "_git_current_tag", return_value=None), \
             patch.object(gs, "_git_is_dirty", return_value=False), \
             patch.object(gs, "cmd_setup", return_value=0) as mock_setup, \
             patch.object(pathlib.Path, "exists", return_value=True), \
             patch.object(gs.subprocess, "run",
                          return_value=MagicMock(returncode=1)):
            rc = gs.cmd_upgrade(["--skills"])

        mock_setup.assert_not_called()
        self.assertEqual(rc, 1)

    def test_skills_flag_stripped_from_install_args(self):
        """--skills is not forwarded to install.sh; extra flags are."""
        with patch.object(gs, "_ghostship_dir", return_value=pathlib.Path("/repo")), \
             patch.object(gs, "_git_current_tag", return_value=None), \
             patch.object(gs, "_git_is_dirty", return_value=False), \
             patch.object(gs, "cmd_setup", return_value=0), \
             patch.object(pathlib.Path, "exists", return_value=True), \
             patch.object(gs.subprocess, "run",
                          return_value=MagicMock(returncode=0)) as mock_run:
            gs.cmd_upgrade(["--skills", "--port", "9999"])

        install_cmd = mock_run.call_args[0][0]
        self.assertNotIn("--skills", install_cmd)
        self.assertIn("--port", install_cmd)
        self.assertIn("9999", install_cmd)
        self.assertIn("bin/install.sh", str(install_cmd[0]))

    def test_no_skills_flag_uses_exec_script(self):
        """Without --skills, _exec_script is called (original behaviour)."""
        with patch.object(gs, "_ghostship_dir", return_value=pathlib.Path("/repo")), \
             patch.object(gs, "_git_current_tag", return_value=None), \
             patch.object(gs, "_git_is_dirty", return_value=False), \
             patch.object(gs, "_exec_script") as mock_exec:
            try:
                gs.cmd_upgrade(["--port", "9999"])
            except SystemExit:
                pass  # execvp would replace the process; mock raises nothing
        mock_exec.assert_called_once_with("bin/install.sh", ["--port", "9999"])

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

    def test_help_includes_yes_flag(self):
        """--help output documents the new --yes flag."""
        out = io.StringIO()
        with patch("sys.stdout", out):
            gs.cmd_upgrade(["--help"])
        self.assertIn("--yes", out.getvalue())


if __name__ == "__main__":
    unittest.main()


# ── cmd_upgrade version detection (TRN-305) ──────────────────────────────────

class TestCmdUpgradeVersionDetection(unittest.TestCase):
    """cmd_upgrade detects current/latest tags and prompts before upgrading."""

    def _patch_dir(self):
        return patch.object(gs, "_ghostship_dir", return_value=pathlib.Path("/repo"))

    # ── Task 3.2: dev branch (not on tag) ────────────────────────────────────

    def test_not_on_tag_rebuilds_without_fetch(self):
        """Not on a release tag: prints rebuild message, does not call git fetch."""
        out = io.StringIO()
        with self._patch_dir(), \
             patch.object(gs, "_git_current_tag", return_value=None), \
             patch.object(gs, "_git_is_dirty", return_value=False), \
             patch.object(gs, "_git_latest_remote_tag") as mock_fetch, \
             patch.object(gs, "_exec_script"), \
             patch("sys.stdout", out):
            gs.cmd_upgrade([])
        mock_fetch.assert_not_called()
        self.assertIn("Not on a release tag", out.getvalue())

    def test_dirty_tree_rebuilds_without_fetch(self):
        """Dirty working tree: prints rebuild message, does not call git fetch."""
        out = io.StringIO()
        with self._patch_dir(), \
             patch.object(gs, "_git_current_tag", return_value="v0.11.0"), \
             patch.object(gs, "_git_is_dirty", return_value=True), \
             patch.object(gs, "_git_latest_remote_tag") as mock_fetch, \
             patch.object(gs, "_exec_script"), \
             patch("sys.stdout", out):
            gs.cmd_upgrade([])
        mock_fetch.assert_not_called()
        self.assertIn("Not on a release tag", out.getvalue())

    # ── Task 3.1: exact-tag checkout — version diff shown, checkout happens ──

    def test_already_on_latest_rebuilds_in_place(self):
        """Already on latest tag: prints 'Already on vX.Y.Z', no checkout."""
        out = io.StringIO()
        with self._patch_dir(), \
             patch.object(gs, "_git_current_tag", return_value="v0.11.1"), \
             patch.object(gs, "_git_is_dirty", return_value=False), \
             patch.object(gs, "_git_latest_remote_tag", return_value="v0.11.1"), \
             patch.object(gs, "_exec_script"), \
             patch("sys.stdout", out):
            gs.cmd_upgrade([])
        self.assertIn("Already on v0.11.1", out.getvalue())

    def test_newer_tag_shows_diff_and_prompts(self):
        """New version available: prints vX → vY, prompts, aborts on 'n'."""
        out = io.StringIO()
        with self._patch_dir(), \
             patch.object(gs, "_git_current_tag", return_value="v0.11.0"), \
             patch.object(gs, "_git_is_dirty", return_value=False), \
             patch.object(gs, "_git_latest_remote_tag", return_value="v0.11.1"), \
             patch.object(gs, "_exec_script") as mock_exec, \
             patch("builtins.input", return_value="n"), \
             patch("sys.stdout", out):
            rc = gs.cmd_upgrade([])
        self.assertEqual(rc, 0)
        mock_exec.assert_not_called()
        self.assertIn("v0.11.0", out.getvalue())
        self.assertIn("v0.11.1", out.getvalue())

    def test_newer_tag_yes_flag_skips_prompt_and_checks_out(self):
        """--yes: skips prompt, runs git checkout, then install."""
        with self._patch_dir(), \
             patch.object(gs, "_git_current_tag", return_value="v0.11.0"), \
             patch.object(gs, "_git_is_dirty", return_value=False), \
             patch.object(gs, "_git_latest_remote_tag", return_value="v0.11.1"), \
             patch.object(gs, "subprocess") as mock_sub, \
             patch.object(gs, "_exec_script") as mock_exec:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            gs.cmd_upgrade(["--yes"])
        # git checkout was called
        checkout_calls = [c for c in mock_sub.run.call_args_list
                          if "checkout" in c[0][0]]
        self.assertEqual(len(checkout_calls), 1)
        checkout_cmd = checkout_calls[0][0][0]
        self.assertIn("tags/v0.11.1", checkout_cmd)
        # install exec was called after checkout
        mock_exec.assert_called_once_with("bin/install.sh", [])

    def test_newer_tag_user_confirms_and_checks_out(self):
        """User types 'y': runs git checkout, then install."""
        with self._patch_dir(), \
             patch.object(gs, "_git_current_tag", return_value="v0.11.0"), \
             patch.object(gs, "_git_is_dirty", return_value=False), \
             patch.object(gs, "_git_latest_remote_tag", return_value="v0.11.1"), \
             patch.object(gs, "subprocess") as mock_sub, \
             patch.object(gs, "_exec_script") as mock_exec, \
             patch("builtins.input", return_value="y"):
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            gs.cmd_upgrade([])
        checkout_calls = [c for c in mock_sub.run.call_args_list
                          if "checkout" in c[0][0]]
        self.assertEqual(len(checkout_calls), 1)
        mock_exec.assert_called_once_with("bin/install.sh", [])

    def test_checkout_failure_returns_1(self):
        """If git checkout fails, returns 1 without running install."""
        with self._patch_dir(), \
             patch.object(gs, "_git_current_tag", return_value="v0.11.0"), \
             patch.object(gs, "_git_is_dirty", return_value=False), \
             patch.object(gs, "_git_latest_remote_tag", return_value="v0.11.1"), \
             patch.object(gs, "subprocess") as mock_sub, \
             patch.object(gs, "_exec_script") as mock_exec, \
             patch("builtins.input", return_value="y"):
            mock_sub.run.return_value = MagicMock(
                returncode=1, stdout="", stderr="detached HEAD error"
            )
            rc = gs.cmd_upgrade([])
        self.assertEqual(rc, 1)
        mock_exec.assert_not_called()

    def test_fetch_failure_falls_through_to_rebuild(self):
        """Cannot reach origin: prints warning, falls through to install."""
        out = io.StringIO()
        with self._patch_dir(), \
             patch.object(gs, "_git_current_tag", return_value="v0.11.0"), \
             patch.object(gs, "_git_is_dirty", return_value=False), \
             patch.object(gs, "_git_latest_remote_tag", return_value=None), \
             patch.object(gs, "_exec_script"), \
             patch("sys.stdout", out):
            gs.cmd_upgrade([])
        self.assertIn("Could not reach origin", out.getvalue())

    def test_yes_flag_stripped_from_install_args(self):
        """--yes is not forwarded to install.sh."""
        with self._patch_dir(), \
             patch.object(gs, "_git_current_tag", return_value=None), \
             patch.object(gs, "_git_is_dirty", return_value=False), \
             patch.object(gs, "_exec_script") as mock_exec:
            gs.cmd_upgrade(["--yes"])
        mock_exec.assert_called_once_with("bin/install.sh", [])


# ── git helper unit tests (TRN-305) ──────────────────────────────────────────

class TestGitHelpers(unittest.TestCase):
    """Unit tests for _git_current_tag, _git_latest_remote_tag, _git_is_dirty."""

    def test_current_tag_returns_tag_on_success(self):
        with patch.object(gs.subprocess, "run",
                          return_value=MagicMock(returncode=0, stdout="v0.11.1\n")):
            self.assertEqual(gs._git_current_tag("/repo"), "v0.11.1")

    def test_current_tag_returns_none_on_nonzero(self):
        with patch.object(gs.subprocess, "run",
                          return_value=MagicMock(returncode=128, stdout="")):
            self.assertIsNone(gs._git_current_tag("/repo"))

    def test_current_tag_returns_none_on_timeout(self):
        with patch.object(gs.subprocess, "run",
                          side_effect=gs.subprocess.TimeoutExpired(["git"], 10)):
            self.assertIsNone(gs._git_current_tag("/repo"))

    def test_latest_remote_tag_returns_first_tag(self):
        def _run(cmd, **_kw):
            if "fetch" in cmd:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0, stdout="v0.11.1\nv0.11.0\nv0.10.2\n")
        with patch.object(gs.subprocess, "run", side_effect=_run):
            self.assertEqual(gs._git_latest_remote_tag("/repo"), "v0.11.1")

    def test_latest_remote_tag_returns_none_on_fetch_failure(self):
        def _run(cmd, **_kw):
            if "fetch" in cmd:
                return MagicMock(returncode=1, stdout="", stderr="network error")
            return MagicMock(returncode=0, stdout="v0.11.1\n")
        out = io.StringIO()
        with patch.object(gs.subprocess, "run", side_effect=_run), \
             patch("sys.stdout", out):
            result = gs._git_latest_remote_tag("/repo")
        self.assertIsNone(result)
        self.assertIn("warning", out.getvalue())

    def test_latest_remote_tag_returns_none_when_no_tags(self):
        def _run(cmd, **_kw):
            return MagicMock(returncode=0, stdout="", stderr="")
        with patch.object(gs.subprocess, "run", side_effect=_run):
            self.assertIsNone(gs._git_latest_remote_tag("/repo"))

    def test_is_dirty_returns_true_when_output_nonempty(self):
        with patch.object(gs.subprocess, "run",
                          return_value=MagicMock(returncode=0, stdout=" M ghostship\n")):
            self.assertTrue(gs._git_is_dirty("/repo"))

    def test_is_dirty_returns_false_when_clean(self):
        with patch.object(gs.subprocess, "run",
                          return_value=MagicMock(returncode=0, stdout="")):
            self.assertFalse(gs._git_is_dirty("/repo"))

    def test_is_dirty_returns_false_on_timeout(self):
        with patch.object(gs.subprocess, "run",
                          side_effect=gs.subprocess.TimeoutExpired(["git"], 10)):
            self.assertFalse(gs._git_is_dirty("/repo"))


# ── portal data volume lookup ────────────────────────────────────────────────

class TestPortalDataMountpoint(unittest.TestCase):
    """status finds the portal volume under its Compose name (ga_ga-portal-data)."""

    def _fake_run(self, existing: dict):
        def _run(cmd, **_kw):
            name = cmd[-1]
            if name in existing:
                return MagicMock(returncode=0, stdout=f'[{{"Mountpoint": "{existing[name]}"}}]')
            return MagicMock(returncode=125, stdout="")
        return _run

    def test_compose_prefixed_name_is_found(self):
        with patch.object(gs.subprocess, "run", side_effect=self._fake_run({"ga_ga-portal-data": "/vol/prefixed"})):
            self.assertEqual(gs._portal_data_mountpoint(["podman"]), "/vol/prefixed")

    def test_bare_name_is_fallback(self):
        with patch.object(gs.subprocess, "run", side_effect=self._fake_run({"ga-portal-data": "/vol/bare"})):
            self.assertEqual(gs._portal_data_mountpoint(["podman"]), "/vol/bare")

    def test_neither_name_returns_none(self):
        with patch.object(gs.subprocess, "run", side_effect=self._fake_run({})):
            self.assertIsNone(gs._portal_data_mountpoint(["podman"]))


# ── macOS CA cert extraction hint (TRN-268) ──────────────────────────────────

class TestCmdStatusMacOSHint(unittest.TestCase):
    """cmd_status prints podman machine ssh extraction hint on macOS only."""

    def _make_volume_run(self, mountpoint: str):
        """Return a subprocess.run side-effect that resolves ga_ga-portal-data volume."""
        def _run(cmd, **_kw):
            # Detect the inspect call for the ga-transport container
            if "ga-transport" in cmd:
                return MagicMock(
                    returncode=0,
                    stdout="running\t2026-01-01T00:00:00Z\t{}",
                    stderr="",
                )
            name = cmd[-1]
            if name == "ga_ga-portal-data":
                return MagicMock(returncode=0, stdout=f'[{{"Mountpoint": "{mountpoint}"}}]')
            return MagicMock(returncode=125, stdout="", stderr="")
        return _run

    def _run_cmd_status_with_platform(self, platform: str, env_overrides: dict | None = None):
        """Run cmd_status with GA_PORTAL_TLS_MODE=internal and the given sys.platform."""
        env = {"GA_PORTAL_TLS_MODE": "internal"}
        if env_overrides:
            env.update(env_overrides)
        out = io.StringIO()
        fake_run = self._make_volume_run("/var/home/user/volumes/ga-portal-data/_data")
        with patch.object(gs.subprocess, "run", side_effect=fake_run), \
             patch.object(gs.shutil, "which", return_value="/usr/bin/podman"), \
             patch.dict(gs.os.environ, env, clear=False), \
             patch.object(gs.sys, "platform", platform), \
             patch("sys.stdout", out):
            gs.cmd_status([])
        return out.getvalue()

    def test_darwin_prints_podman_machine_ssh(self):
        """On darwin, stdout contains the podman machine ssh extraction command."""
        output = self._run_cmd_status_with_platform("darwin")
        self.assertIn("podman machine ssh", output)
        self.assertIn("security add-trusted-cert", output)

    def test_linux_does_not_print_extraction_hint(self):
        """On linux, stdout does not contain the macOS extraction hint."""
        output = self._run_cmd_status_with_platform("linux")
        self.assertNotIn("podman machine ssh", output)
        self.assertNotIn("security add-trusted-cert", output)

    def test_darwin_uses_ga_machine_name_env(self):
        """GA_MACHINE_NAME overrides the default machine name in the hint."""
        output = self._run_cmd_status_with_platform(
            "darwin", env_overrides={"GA_MACHINE_NAME": "my-custom-machine"}
        )
        self.assertIn("my-custom-machine", output)

    def test_darwin_default_machine_name(self):
        """Default machine name is ghost-academy when GA_MACHINE_NAME is unset."""
        env = {"GA_PORTAL_TLS_MODE": "internal"}
        out = io.StringIO()
        fake_run = self._make_volume_run("/var/home/user/volumes/ga-portal-data/_data")
        with patch.object(gs.subprocess, "run", side_effect=fake_run), \
             patch.object(gs.shutil, "which", return_value="/usr/bin/podman"), \
             patch.dict(gs.os.environ, env, clear=False), \
             patch.object(gs.sys, "platform", "darwin"), \
             patch("sys.stdout", out):
            gs.os.environ.pop("GA_MACHINE_NAME", None)
            gs.cmd_status([])
        self.assertIn("ghost-academy", out.getvalue())


# ── _inspect_installed_url exception narrowing (TRN-290) ─────────────────────

class TestInspectInstalledUrlExceptionNarrowing(unittest.TestCase):
    """_inspect_installed_url returns '' on subprocess failure and malformed JSON (task 1.6)."""

    def test_returns_empty_string_on_nonzero_returncode(self):
        """Returns '' when podman inspect exits non-zero (missing container)."""
        with patch.object(gs, "_find_podman", return_value=["podman"]), \
             patch.object(gs.subprocess, "run",
                          return_value=MagicMock(returncode=125, stdout="", stderr="Error: no container")):
            result = gs._inspect_installed_url()
        self.assertEqual(result, "")

    def test_returns_empty_string_on_malformed_json(self):
        """Returns '' when podman inspect returns malformed JSON output."""
        with patch.object(gs, "_find_podman", return_value=["podman"]), \
             patch.object(gs.subprocess, "run",
                          return_value=MagicMock(returncode=0, stdout="not-valid-json")):
            result = gs._inspect_installed_url()
        self.assertEqual(result, "")

    def test_returns_url_on_valid_output(self):
        """Returns the GA_HOST_URL value when podman inspect succeeds."""
        env_json = '["GA_HOST_URL=https://example.com", "OTHER=val"]'
        with patch.object(gs, "_find_podman", return_value=["podman"]), \
             patch.object(gs.subprocess, "run",
                          return_value=MagicMock(returncode=0, stdout=env_json)):
            result = gs._inspect_installed_url()
        self.assertEqual(result, "https://example.com")

    def test_returns_empty_when_no_ga_host_url_in_env(self):
        """Returns '' when env list has no GA_HOST_URL entry."""
        env_json = '["OTHER=val", "ANOTHER=foo"]'
        with patch.object(gs, "_find_podman", return_value=["podman"]), \
             patch.object(gs.subprocess, "run",
                          return_value=MagicMock(returncode=0, stdout=env_json)):
            result = gs._inspect_installed_url()
        self.assertEqual(result, "")

    def test_returns_empty_when_podman_not_found(self):
        """Returns '' when _find_podman returns None (podman binary absent)."""
        with patch.object(gs, "_find_podman", return_value=None):
            result = gs._inspect_installed_url()
        self.assertEqual(result, "")

    def test_returns_empty_on_timeout(self):
        """Returns '' when subprocess raises TimeoutExpired."""
        with patch.object(gs, "_find_podman", return_value=["podman"]), \
             patch.object(gs.subprocess, "run",
                          side_effect=subprocess.TimeoutExpired(["podman"], 5)):
            result = gs._inspect_installed_url()
        self.assertEqual(result, "")
