"""Unit tests for bin/lib/wizard.py.

Tests run without terminal, Podman, or any live transport.
I/O is injected via input_fn/print_fn parameters.

Coverage:
(a) Unknown backend re-prompts rather than exiting.
(b) Existing config with _overwrite=n returns without writing.
(c) kiro backend prompts for identity-provider URL.
(d) post-install auth skips already-configured backends.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from bin.lib.wizard import interactive_setup, post_install_auth


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_inputs(*responses: str):
    """Return an input_fn that feeds canned responses one at a time."""
    it = iter(responses)

    def _input(prompt: str = "") -> str:
        try:
            return next(it)
        except StopIteration:
            return ""

    return _input


def _make_print() -> tuple[list[str], callable]:
    """Return (log, print_fn)."""
    log: list[str] = []

    def _print(*args, **kwargs) -> None:
        log.append(" ".join(str(a) for a in args))

    return log, _print


# ---------------------------------------------------------------------------
# (a) Unknown backend re-prompts
# ---------------------------------------------------------------------------

class TestUnknownBackendReprompts:
    def test_unknown_default_backend_reprompts(self, tmp_path: Path) -> None:
        """An unknown default backend should print an error and prompt again."""
        log, print_fn = _make_print()
        inputs = _make_inputs(
            "badbackend",  # first answer: unknown
            "kiro",        # second answer: valid
            "",            # no extra backends
        )
        env = {"GHOSTSHIP_DIR": str(tmp_path)}
        result = interactive_setup(env, input_fn=inputs, print_fn=print_fn)
        assert result["ga_crew_agent"] == "kiro"
        assert any("Unknown backend" in line for line in log)

    def test_valid_backend_accepted_first_try(self, tmp_path: Path) -> None:
        inputs = _make_inputs("kiro", "")
        log, print_fn = _make_print()
        env = {"GHOSTSHIP_DIR": str(tmp_path)}
        result = interactive_setup(env, input_fn=inputs, print_fn=print_fn)
        assert result["ga_crew_agent"] == "kiro"
        assert not any("Unknown backend" in line for line in log)

    def test_unknown_extra_backend_reprompts(self, tmp_path: Path) -> None:
        inputs = _make_inputs(
            "kiro",         # default backend
            "alien",        # unknown extra
            "",             # blank = no extras
        )
        log, print_fn = _make_print()
        env = {"GHOSTSHIP_DIR": str(tmp_path)}
        result = interactive_setup(env, input_fn=inputs, print_fn=print_fn)
        assert result["ga_crew_agent"] == "kiro"
        assert any("Unknown backend" in line for line in log)


# ---------------------------------------------------------------------------
# (b) Existing config with overwrite=n returns without writing
# ---------------------------------------------------------------------------

class TestExistingConfigNotOverwritten:
    def test_no_overwrite_keeps_existing_file(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        yaml_path = config_dir / "ghostship.yaml"
        yaml_path.write_text("# original\n", encoding="utf-8")

        inputs = _make_inputs(
            "kiro",  # default backend
            "",      # no extras
            "n",     # overwrite? → no
        )
        log, print_fn = _make_print()
        env = {"GHOSTSHIP_DIR": str(tmp_path)}
        result = interactive_setup(env, input_fn=inputs, print_fn=print_fn)

        assert yaml_path.read_text(encoding="utf-8") == "# original\n"
        assert result["wrote_config"] is False
        assert any("Keeping existing" in line for line in log)

    def test_overwrite_yes_replaces_file(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        yaml_path = config_dir / "ghostship.yaml"
        yaml_path.write_text("# old\n", encoding="utf-8")

        inputs = _make_inputs(
            "kiro",  # default backend
            "",      # no extras
            "",      # identity provider URL (blank)
            "y",     # overwrite? → yes
        )
        log, print_fn = _make_print()
        env = {"GHOSTSHIP_DIR": str(tmp_path)}
        result = interactive_setup(env, input_fn=inputs, print_fn=print_fn)

        assert yaml_path.read_text(encoding="utf-8") != "# old\n"
        assert result["wrote_config"] is True


# ---------------------------------------------------------------------------
# (c) kiro backend prompts for identity-provider URL
# ---------------------------------------------------------------------------

class TestKiroIdentityProviderPrompt:
    def test_kiro_prompts_for_identity_provider(self, tmp_path: Path) -> None:
        inputs = _make_inputs(
            "kiro",                            # default backend
            "",                                # no extras
            "https://identity.example.com",    # identity provider URL
            "us-east-1",                       # region
        )
        log, print_fn = _make_print()
        env = {"GHOSTSHIP_DIR": str(tmp_path)}
        result = interactive_setup(env, input_fn=inputs, print_fn=print_fn)

        assert result["kiro_identity_provider"] == "https://identity.example.com"
        assert result["kiro_region"] == "us-east-1"

    def test_kiro_skips_region_when_no_provider(self, tmp_path: Path) -> None:
        inputs = _make_inputs(
            "kiro",   # default backend
            "",       # no extras
            "",       # blank identity provider → no region prompt
        )
        log, print_fn = _make_print()
        env = {"GHOSTSHIP_DIR": str(tmp_path)}
        result = interactive_setup(env, input_fn=inputs, print_fn=print_fn)

        assert result["kiro_identity_provider"] == ""
        assert result["kiro_region"] == ""


# ---------------------------------------------------------------------------
# (d) post-install auth skips already-configured backends
# ---------------------------------------------------------------------------

class TestPostInstallAuth:
    def test_skips_configured_backends(self, tmp_path: Path) -> None:
        log, print_fn = _make_print()
        login_calls: list = []

        def _mock_run(cmd, **kwargs):
            if cmd[1:3] == ["auth", "status"]:
                return subprocess.CompletedProcess(
                    cmd, 0,
                    stdout='{"kiro": {"configured": true}, "claude": {"configured": false}}',
                    stderr="",
                )
            if cmd[1:3] == ["auth", "login"]:
                login_calls.append(cmd[3])
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        env = {"GA_CREW_AGENT": "kiro,claude"}
        post_install_auth(
            env,
            str(tmp_path / "ghostship"),
            print_fn=print_fn,
            run=_mock_run,
        )

        assert "claude" in login_calls
        assert "kiro" not in login_calls

    def test_offers_login_when_status_call_fails(self, tmp_path: Path) -> None:
        """If ghostship auth status fails, offer login for all backends."""
        log, print_fn = _make_print()
        login_calls: list = []

        def _mock_run(cmd, **kwargs):
            if cmd[1:3] == ["auth", "status"]:
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="error")
            if cmd[1:3] == ["auth", "login"]:
                login_calls.append(cmd[3])
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        env = {"GA_CREW_AGENT": "kiro"}
        post_install_auth(
            env,
            str(tmp_path / "ghostship"),
            print_fn=print_fn,
            run=_mock_run,
        )

        assert "kiro" in login_calls

    def test_all_configured_skips_all(self, tmp_path: Path) -> None:
        log, print_fn = _make_print()
        login_calls: list = []

        def _mock_run(cmd, **kwargs):
            if cmd[1:3] == ["auth", "status"]:
                return subprocess.CompletedProcess(
                    cmd, 0,
                    stdout='{"kiro": {"configured": true}}',
                    stderr="",
                )
            if cmd[1:3] == ["auth", "login"]:
                login_calls.append(cmd[3])
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        env = {"GA_CREW_AGENT": "kiro"}
        post_install_auth(
            env,
            str(tmp_path / "ghostship"),
            print_fn=print_fn,
            run=_mock_run,
        )

        assert login_calls == []
        assert any("already configured" in line for line in log)
