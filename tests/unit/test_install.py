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

import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = REPO_ROOT / "bin" / "install.sh"

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


# ── Static assertions on install.sh ──────────────────────────────────────────

class TestInstallSecretWiring:
    """install.sh no longer wires any backend credential Podman secret."""

    def test_no_credential_secret_create_or_rm(self, install_sh_text: str) -> None:
        for name in CREDENTIAL_SECRET_NAMES:
            assert not re.search(
                rf"secret\s+(?:create|rm)\s+{re.escape(name)}\b", install_sh_text
            ), f"install.sh still runs 'secret create|rm {name}'"

    def test_no_credential_compose_secret_lines(self, install_sh_text: str) -> None:
        # The compose template must not list the credential secrets as a mount
        # or as a top-level external secret.
        for name in CREDENTIAL_SECRET_NAMES:
            assert f"- {name}" not in install_sh_text, (
                f"install.sh compose template still mounts secret {name}"
            )
            assert f"  {name}:" not in install_sh_text, (
                f"install.sh compose template still declares secret {name}"
            )

    def test_transport_bearer_secret_still_wired(self, install_sh_text: str) -> None:
        # The non-credential secrets (bearer key, transport secret) are untouched.
        assert "secret create ga-api-key" in install_sh_text or (
            "ga-api-key" in install_sh_text
        )
        assert "ga-transport-secret" in install_sh_text


class TestDeprecatedModelKeyNames:
    """Credential vars warn-and-ignore; base-URL aliases still map."""

    def test_ignored_setting_warning_block_present(self, install_sh_text: str) -> None:
        assert "no longer used by the installer and is ignored" in install_sh_text
        # Every ignored var appears in the warning loop's name list.
        for var in IGNORED_CREDENTIAL_VARS:
            assert var in install_sh_text, f"{var} missing from install.sh"

    def test_base_url_aliases_still_mapped(self, install_sh_text: str) -> None:
        # The alias-mapping loop still handles the two base-URL names.
        assert "for _new in ANTHROPIC_BASE_URL OPENAI_BASE_URL" in install_sh_text
        # And it must NOT map the credential names any more.
        assert "ANTHROPIC_API_KEY OPENAI_BASE_URL" not in install_sh_text


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
def test_base_url_alias_maps_in_bash(install_sh_text: str, tmp_path: Path) -> None:
    body = _extract_loops(install_sh_text)
    script = textwrap.dedent(
        """\
        set -euo pipefail
        GA_CREW_ANTHROPIC_BASE_URL="https://proxy.example/v1"
        """
    ) + body + '\necho "RESULT_ANTHROPIC_BASE_URL=${ANTHROPIC_BASE_URL:-}"\n'
    sp = tmp_path / "run.sh"
    sp.write_text(script, encoding="utf-8")
    proc = subprocess.run(
        [BASH, str(sp)], capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, proc.stderr
    assert "RESULT_ANTHROPIC_BASE_URL=https://proxy.example/v1" in proc.stdout
    assert "deprecated" in proc.stderr


@pytest.mark.skipif(not BASH, reason="bash not available")
@pytest.mark.parametrize("var", IGNORED_CREDENTIAL_VARS)
def test_ignored_credential_warns_and_unsets_in_bash(
    install_sh_text: str, tmp_path: Path, var: str
) -> None:
    body = _extract_loops(install_sh_text)
    script = textwrap.dedent(
        f"""\
        set -euo pipefail
        {var}="sk-should-be-ignored-secret-value"
        """
    ) + body + f'\necho "RESULT_{var}=${{{var}:-<unset>}}"\n'
    sp = tmp_path / "run.sh"
    sp.write_text(script, encoding="utf-8")
    proc = subprocess.run(
        [BASH, str(sp)], capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, proc.stderr
    # The warning fires naming the ignored variable...
    assert f"WARNING: {var} is no longer used" in proc.stderr
    # ...the variable is unset so it cannot reach the compose file...
    assert f"RESULT_{var}=<unset>" in proc.stdout
    # ...and the secret value never appears on stdout.
    assert "sk-should-be-ignored-secret-value" not in proc.stdout


# ── Wizard: Identity Center prompts stay, auth-login hints dropped (5.2) ──────

class TestWizardAuth:
    """The interactive wizard keeps Kiro Identity Center prompts, drops the
    static ``auth login anthropic|openai`` hints, and offers a per-backend login
    for each enabled, unconfigured backend after the transport is ready."""

    def test_kiro_identity_center_prompts_kept(self, install_sh_text: str) -> None:
        assert "identity provider URL" in install_sh_text
        assert "KIRO_IDENTITY_PROVIDER" in install_sh_text
        assert "KIRO_REGION" in install_sh_text

    def test_anthropic_openai_login_hints_dropped(self, install_sh_text: str) -> None:
        # The old backend-named hints must be gone.
        assert "auth login anthropic" not in install_sh_text
        assert "auth login openai" not in install_sh_text

    def test_post_transport_offers_login_per_backend(self, install_sh_text: str) -> None:
        # The authentication block queries status and loops over enabled backends.
        assert "ghostship" in install_sh_text and "auth status --json" in install_sh_text
        assert "auth login" in install_sh_text
        assert "_enabled_backends" in install_sh_text


def _extract_auth_block(install_sh_text: str) -> str:
    start = install_sh_text.index(
        "# ── Interactive-mode authentication (TRN-233)"
    )
    end_marker = "unset _enabled_backends _auth_status_json _backend _is_configured"
    end = install_sh_text.index(end_marker) + len(end_marker)
    block = install_sh_text[start:end]
    # The real block is wrapped in `if INTERACTIVE ... fi`; our slice stops at
    # the `unset` line (before `fi`), so append the closing `fi` to balance it.
    return block + "\nfi\n"


@pytest.mark.skipif(not BASH, reason="bash not available")
def test_wizard_offers_login_only_for_unconfigured_backend(
    install_sh_text: str, tmp_path: Path
) -> None:
    """Scripted run against a keyed install: kiro already configured, claude not.

    A stub `ghostship` returns a status JSON marking kiro configured and claude
    unconfigured, and records any `auth login <backend>` call. The loop must
    skip kiro and invoke login for claude only.
    """
    if not shutil.which("python3"):
        pytest.skip("python3 not available")

    ghostship_dir = tmp_path
    calls = tmp_path / "login_calls.txt"
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
              echo "$3" >> "{calls}"
              exit 0
            fi
            exit 0
            """
        ),
        encoding="utf-8",
    )
    stub.chmod(0o755)

    body = _extract_auth_block(install_sh_text)
    script = (
        textwrap.dedent(
            f"""\
            set -uo pipefail
            GHOSTSHIP_DIR="{ghostship_dir}"
            _INTERACTIVE_MODE=true
            GA_CREW_AGENT="kiro,claude"
            """
        )
        + body
    )
    sp = tmp_path / "run.sh"
    sp.write_text(script, encoding="utf-8")
    proc = subprocess.run(
        [BASH, str(sp)], capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, proc.stderr
    logged = calls.read_text(encoding="utf-8").split() if calls.exists() else []
    assert "claude" in logged, f"expected a claude login, got {logged!r}"
    assert "kiro" not in logged, f"kiro was already configured, got {logged!r}"
    assert "already configured" in proc.stdout

