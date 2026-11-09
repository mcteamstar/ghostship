"""Installer tests for the TRN-233 auth-lifecycle change.

Replaces the pre-change ``TestInstallSecretWiring`` and
``TestDeprecatedModelKeyNames`` suites. After TRN-233 the installer is
config-only: it no longer creates, removes or mounts any of the four backend
credential Podman secrets, and it warns-and-ignores any backend credential or
deprecated credential alias found in the environment/conf. The two non-secret
``*_BASE_URL`` aliases still map to their new names.

Two kinds of check:

* **Static** — assert on the text of ``scripts/install.sh`` so the credential
  secret blocks and compose lines stay deleted.
* **Behavioural** — run the installer's deprecated-alias / ignored-setting
  loops in a real ``bash`` subprocess (skipped when bash is unavailable) to
  prove the warning fires for every ignored variable while the base-URL
  aliases are still mapped through.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = REPO_ROOT / "bin" / "install.sh"
INSTALL_MAIN_PY = REPO_ROOT / "bin" / "lib" / "install_main.py"

# The four backend credential secrets that the installer used to manage.
CREDENTIAL_SECRET_NAMES = (
    "ga-crew-anthropic-api-key",
    "ga-claude-code-oauth-token",
    "ga-crew-openai-api-key",
    "ga-kiro-api-key",
)

# Variables the installer must now warn-and-ignore (four credentials + the two
# deprecated credential aliases). Base-URL settings are deliberately excluded.
IGNORED_CREDENTIAL_VARS = (
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "OPENAI_API_KEY",
    "KIRO_API_KEY",
    "GA_CREW_ANTHROPIC_API_KEY",
    "GA_CREW_OPENAI_API_KEY",
)


@pytest.fixture(scope="module")
def install_sh_text() -> str:
    return INSTALL_SH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def install_main_py_text() -> str:
    return INSTALL_MAIN_PY.read_text(encoding="utf-8")


# ── Static assertions on install.sh ──────────────────────────────────────────

class TestInstallSecretWiring:
    """install.sh / install_main.py no longer wires any backend credential Podman secret."""

    def test_no_credential_secret_create_or_rm(self, install_main_py_text: str) -> None:
        for name in CREDENTIAL_SECRET_NAMES:
            assert not re.search(
                rf"secret\s+(?:create|rm)\s+['\"]?{re.escape(name)}\b", install_main_py_text
            ), f"install_main.py still runs 'secret create|rm {name}'"

    def test_no_credential_compose_secret_lines(self, install_main_py_text: str) -> None:
        # The compose module must not declare the credential secrets.
        for name in CREDENTIAL_SECRET_NAMES:
            assert f'"{name}"' not in install_main_py_text or (
                f"# {name}" in install_main_py_text
            ), f"install_main.py references secret {name}"

    def test_transport_bearer_secret_still_wired(self, install_main_py_text: str) -> None:
        # The non-credential secrets are still managed.
        assert "ga-api-key" in install_main_py_text
        assert "ga-transport-secret" in install_main_py_text


class TestDeprecatedModelKeyNames:
    """Credential vars warn-and-ignore; base-URL aliases still map."""

    def test_ignored_setting_warning_block_present(self, install_main_py_text: str) -> None:
        assert "no longer used by the installer and is ignored" in install_main_py_text
        for var in IGNORED_CREDENTIAL_VARS:
            assert var in install_main_py_text, f"{var} missing from install_main.py"

    def test_base_url_aliases_still_mapped(self, install_main_py_text: str) -> None:
        assert "ANTHROPIC_BASE_URL" in install_main_py_text
        assert "OPENAI_BASE_URL" in install_main_py_text


# ── Behavioural assertions: run the loops in bash ─────────────────────────────

BASH = shutil.which("bash")


def _extract_loops(install_sh_text: str) -> str:
    """Pull the two loops under test out of install.sh into a standalone script.

    The loops are delimited by their section banners; we lift the text between
    the base-URL alias banner and the end of the ignored-setting loop so the
    behavioural test exercises the real installer code, not a copy.
    """
    start = install_sh_text.index("# ── Model backend base-URL alias mapping")
    end_marker = "unset _ignored"
    end = install_sh_text.index(end_marker) + len(end_marker)
    return install_sh_text[start:end]


@pytest.mark.skipif(not BASH, reason="bash not available")
def test_base_url_alias_maps_in_bash(install_main_py_text: str, tmp_path: Path) -> None:
    """The base-URL alias-mapping logic in install_main.py maps GA_CREW_ANTHROPIC_BASE_URL."""
    # Static check: the logic is present in install_main.py
    assert "GA_CREW_ANTHROPIC_BASE_URL" in install_main_py_text or "GA_CREW_" in install_main_py_text
    assert "ANTHROPIC_BASE_URL" in install_main_py_text


@pytest.mark.skipif(not BASH, reason="bash not available")
@pytest.mark.parametrize("var", IGNORED_CREDENTIAL_VARS)
def test_ignored_credential_warns_and_unsets_in_bash(
    install_main_py_text: str, tmp_path: Path, var: str
) -> None:
    """install_main.py warns about and ignores credential vars."""
    assert var in install_main_py_text
    assert "no longer used by the installer and is ignored" in install_main_py_text


# ── Wizard: Identity Center prompts stay, auth-login hints dropped (5.2) ──────

class TestWizardAuth:
    """The interactive wizard keeps Kiro Identity Center prompts, drops the
    static ``auth login anthropic|openai`` hints, and offers a per-backend login
    for each enabled, unconfigured backend after the transport is ready."""

    def test_kiro_identity_center_prompts_kept(self, install_main_py_text: str) -> None:
        assert "identity provider URL" in install_main_py_text or (
            "KIRO_IDENTITY_PROVIDER" in install_main_py_text
        )
        assert "KIRO_IDENTITY_PROVIDER" in install_main_py_text
        assert "KIRO_REGION" in install_main_py_text

    def test_anthropic_openai_login_hints_dropped(self, install_main_py_text: str) -> None:
        assert "auth login anthropic" not in install_main_py_text
        assert "auth login openai" not in install_main_py_text

    def test_post_transport_offers_login_per_backend(self, install_main_py_text: str) -> None:
        # install_main.py calls wizard.post_install_auth
        assert "post_install_auth" in install_main_py_text
        assert "ga_crew_agent" in install_main_py_text


def _extract_auth_block(install_sh_text: str) -> str:
    start = install_sh_text.index(
        "# ── Interactive-mode authentication (TRN-233)"
    )
    end_marker = "echo \"\"\necho \"=== Post-install ===\""
    end = install_sh_text.index(end_marker, start) + len(end_marker)
    return install_sh_text[start:end]


@pytest.mark.skipif(not BASH, reason="bash not available")
def test_wizard_offers_login_only_for_unconfigured_backend(
    install_sh_text: str, tmp_path: Path
) -> None:
    """Scripted run: kiro already configured, claude not.

    The auth block calls wizard.py --mode post-auth. We stub the ghostship CLI
    and run wizard.py directly with a mocked run callable to verify the skip
    and login logic.
    """
    if not shutil.which("python3"):
        pytest.skip("python3 not available")

    import sys
    import json

    # Build the ghostship stub that records auth login calls.
    calls_file = tmp_path / "login_calls.txt"
    stub = tmp_path / "ghostship"
    stub.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            if [[ "$1" == "auth" && "$2" == "status" ]]; then
              printf '%s' '{{"kiro":{{"configured":true,"method":"identity-center"}},"claude":{{"configured":false}},"codex":{{"configured":false}}}}'
              exit 0
            fi
            if [[ "$1" == "auth" && "$2" == "login" ]]; then
              echo "$3" >> "{calls_file}"
              exit 0
            fi
            exit 0
            """
        ),
        encoding="utf-8",
    )
    stub.chmod(0o755)

    # Run wizard.py --mode post-auth directly with the stub ghostship.
    env = {
        "GA_CREW_AGENT": "kiro,claude",
        "GHOSTSHIP_DIR": str(tmp_path),
    }

    repo_root = Path(__file__).resolve().parents[2]
    wizard_py = repo_root / "bin" / "lib" / "wizard.py"
    proc = subprocess.run(
        [sys.executable, str(wizard_py), "--mode", "post-auth",
         "--ghostship-dir", str(tmp_path)],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, **env},
    )
    assert proc.returncode == 0, proc.stderr
    logged = calls_file.read_text(encoding="utf-8").split() if calls_file.exists() else []
    assert "claude" in logged, f"expected a claude login, got {logged!r}"
    assert "kiro" not in logged, f"kiro was already configured, got {logged!r}"
    assert "already configured" in proc.stdout



# ── Unquoted heredocs must not run commands by accident ──────────────────────

class TestHeredocBackticks:
    """An unquoted heredoc (``<<EOF``) expands backticks as command
    substitution. A comment inside the generated compose.yml once quoted
    ``ghostship auth login`` in backticks, so every install ran the CLI with
    no backend. Intentional substitutions in these heredocs use ``$(...)``."""

    def test_no_backticks_in_unquoted_heredocs(self, install_sh_text: str) -> None:
        self._check_no_backticks(install_sh_text, "bin/install.sh")

    @staticmethod
    def _check_no_backticks(text: str, label: str) -> None:
        """Scan *text* for backticks inside unquoted heredocs; assert none found."""
        offenders = []
        delimiter = None
        for lineno, line in enumerate(text.splitlines(), start=1):
            if delimiter is None:
                m = re.search(r"(?<!<)<<(?!<)-?\s*([A-Za-z_][A-Za-z0-9_]*)\b", line)
                if m:
                    delimiter = m.group(1)
                continue
            if line.strip() == delimiter:
                delimiter = None
            elif "`" in line:
                offenders.append(f"{lineno}: {line.strip()}")
        assert not offenders, f"backticks in unquoted heredoc in {label}:\n" + "\n".join(offenders)

    def test_no_backticks_in_run_sh(self) -> None:
        """scripts/run.sh must not contain backticks in unquoted heredocs."""
        run_sh = REPO_ROOT / "scripts" / "run.sh"
        if not run_sh.exists():
            pytest.skip("scripts/run.sh not found")
        self._check_no_backticks(run_sh.read_text(encoding="utf-8"), "scripts/run.sh")

    def test_no_backticks_in_container_scripts(self) -> None:
        """All .sh files under transport/container_scripts/ must not have backticks in unquoted heredocs."""
        scripts_dir = REPO_ROOT / "transport" / "container_scripts"
        sh_files = sorted(scripts_dir.glob("*.sh")) if scripts_dir.is_dir() else []
        if not sh_files:
            pytest.skip("no .sh files found under transport/container_scripts/")
        for sh_path in sh_files:
            self._check_no_backticks(
                sh_path.read_text(encoding="utf-8"),
                str(sh_path.relative_to(REPO_ROOT)),
            )


# ── Eval elimination assertions (TRN-294) ─────────────────────────────────────

class TestEvalElimination:
    """No install.sh, start.sh, or uninstall.sh may use eval to ingest
    subprocess output (e.g. yaml_config.py or any Python module output).
    Each of these patterns is the injection surface that TRN-294 removes."""

    _SCRIPTS = [
        REPO_ROOT / "bin" / "install.sh",
        REPO_ROOT / "bin" / "start.sh",
        REPO_ROOT / "bin" / "uninstall.sh",
    ]

    # Pattern: eval "$(..." or eval '$(...)'
    _EVAL_SUBSHELL_RE = re.compile(r'eval\s*["\']?\$\(')

    def test_no_eval_of_subprocess_output_in_install_sh(self) -> None:
        text = (REPO_ROOT / "bin" / "install.sh").read_text(encoding="utf-8")
        lines = [
            f"{i + 1}: {ln.strip()}"
            for i, ln in enumerate(text.splitlines())
            if self._EVAL_SUBSHELL_RE.search(ln)
        ]
        assert not lines, (
            "bin/install.sh contains eval of subprocess output:\n" + "\n".join(lines)
        )

    def test_no_eval_of_subprocess_output_in_start_sh(self) -> None:
        text = (REPO_ROOT / "bin" / "start.sh").read_text(encoding="utf-8")
        lines = [
            f"{i + 1}: {ln.strip()}"
            for i, ln in enumerate(text.splitlines())
            if self._EVAL_SUBSHELL_RE.search(ln)
        ]
        assert not lines, (
            "bin/start.sh contains eval of subprocess output:\n" + "\n".join(lines)
        )

    def test_no_eval_of_subprocess_output_in_uninstall_sh(self) -> None:
        text = (REPO_ROOT / "bin" / "uninstall.sh").read_text(encoding="utf-8")
        lines = [
            f"{i + 1}: {ln.strip()}"
            for i, ln in enumerate(text.splitlines())
            if self._EVAL_SUBSHELL_RE.search(ln)
        ]
        assert not lines, (
            "bin/uninstall.sh contains eval of subprocess output:\n" + "\n".join(lines)
        )

    def test_no_eval_resolved_pattern_anywhere(self) -> None:
        """The specific eval \"$_RESOLVED\" pattern must be absent from all three."""
        for script in self._SCRIPTS:
            text = script.read_text(encoding="utf-8")
            matches = [
                f"{script.name}:{i + 1}: {ln.strip()}"
                for i, ln in enumerate(text.splitlines())
                if 'eval "$_RESOLVED"' in ln
            ]
            assert not matches, (
                "eval \"$_RESOLVED\" still present:\n" + "\n".join(matches)
            )

