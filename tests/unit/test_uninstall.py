"""Uninstaller tests for the TRN-233 auth-lifecycle change.

After TRN-233, ``scripts/uninstall.sh``:

* keeps ``DATA_DIR/credentials/`` by default (removed only with ``--purge-auth``),
  exactly as it already keeps ``ga-kiro-auth``;
* removes the four obsolete backend credential Podman secrets by name.

The data-dir derivation differs by OS (``Library/Application Support`` on
macOS, ``.local/share`` on Linux); both are asserted statically. The default
and ``--purge-auth`` cleanup paths are exercised behaviourally against a temp
data directory.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
UNINSTALL_SH = REPO_ROOT / "bin" / "uninstall.sh"

OBSOLETE_SECRET_NAMES = (
    "ga-crew-anthropic-api-key",
    "ga-claude-code-oauth-token",
    "ga-crew-openai-api-key",
    "ga-kiro-api-key",
)

BASH = shutil.which("bash")


@pytest.fixture(scope="module")
def uninstall_sh_text() -> str:
    return UNINSTALL_SH.read_text(encoding="utf-8")


# ── Static assertions ─────────────────────────────────────────────────────────

class TestUninstallCredentialSecrets:
    def test_removes_each_obsolete_secret_by_name(self, uninstall_sh_text: str) -> None:
        for name in OBSOLETE_SECRET_NAMES:
            assert name in uninstall_sh_text, f"{name} missing from uninstall.sh"
        assert 'secret rm "${_obsolete_secret}"' in uninstall_sh_text

    def test_credentials_dir_preserved_by_default(self, uninstall_sh_text: str) -> None:
        assert 'CREDENTIALS_DIR="${DATA_DIR}/credentials"' in uninstall_sh_text
        # The cleanup loop skips the credentials dir.
        assert '[[ "$entry" == "$CREDENTIALS_DIR" ]] && continue' in uninstall_sh_text

    def test_data_dir_paths_both_os(self, uninstall_sh_text: str) -> None:
        # macOS and Linux data-dir derivations are both present.
        assert "Library/Application Support" in uninstall_sh_text
        assert ".local/share" in uninstall_sh_text


# ── Behavioural: run the data-dir cleanup loop ────────────────────────────────

def _extract_datadir_cleanup(uninstall_sh_text: str) -> str:
    start = uninstall_sh_text.index('AUTH_FILE="${DATA_DIR}/ga-kiro-auth"')
    end_marker = 'echo "✓ removed transport state from ${DATA_DIR} (kept'
    pos = uninstall_sh_text.index(end_marker)
    # Two `fi` close the block: the inner if/else (PURGE_AUTH) then the outer
    # `if [[ -d "$DATA_DIR" ]]`. Capture through the second.
    first_fi = uninstall_sh_text.index("fi", pos)
    second_fi = uninstall_sh_text.index("fi", first_fi + 2) + len("fi")
    return uninstall_sh_text[start:second_fi]


def _seed_data_dir(base: Path) -> Path:
    data = base / "data"
    (data / "credentials").mkdir(parents=True)
    (data / "credentials" / "kiro.json").write_text("{}", encoding="utf-8")
    (data / "ga-kiro-auth").write_text("auth", encoding="utf-8")
    (data / "compose.yml").write_text("services: {}", encoding="utf-8")
    (data / "academy").mkdir()
    return data


@pytest.mark.skipif(not BASH, reason="bash not available")
def test_default_uninstall_keeps_credentials(uninstall_sh_text: str, tmp_path: Path) -> None:
    data = _seed_data_dir(tmp_path)
    body = _extract_datadir_cleanup(uninstall_sh_text)
    script = f'set -uo pipefail\nDATA_DIR="{data}"\nPURGE_AUTH=""\n' + body + "\n"
    sp = tmp_path / "run.sh"
    sp.write_text(script, encoding="utf-8")
    proc = subprocess.run([BASH, str(sp)], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert (data / "credentials" / "kiro.json").exists(), "credentials wiped without --purge-auth"
    assert (data / "ga-kiro-auth").exists(), "ga-kiro-auth wiped without --purge-auth"
    assert not (data / "compose.yml").exists(), "transport state not removed"
    assert not (data / "academy").exists(), "transport state not removed"


@pytest.mark.skipif(not BASH, reason="bash not available")
def test_purge_auth_removes_credentials(uninstall_sh_text: str, tmp_path: Path) -> None:
    data = _seed_data_dir(tmp_path)
    body = _extract_datadir_cleanup(uninstall_sh_text)
    script = f'set -uo pipefail\nDATA_DIR="{data}"\nPURGE_AUTH="1"\n' + body + "\n"
    sp = tmp_path / "run.sh"
    sp.write_text(script, encoding="utf-8")
    proc = subprocess.run([BASH, str(sp)], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert not (data / "credentials").exists(), "credentials kept despite --purge-auth"
    assert not (data / "ga-kiro-auth").exists(), "ga-kiro-auth kept despite --purge-auth"


@pytest.mark.skipif(not BASH, reason="bash not available")
def test_obsolete_secret_removal_loop_runs(uninstall_sh_text: str, tmp_path: Path) -> None:
    """The secret-removal loop calls `secret rm` for each of the four names."""
    start = uninstall_sh_text.index("# ── Obsolete credential Podman secrets")
    end = uninstall_sh_text.index("unset _obsolete_secret") + len("unset _obsolete_secret")
    body = uninstall_sh_text[start:end]
    calls = tmp_path / "secret_rm_calls.txt"
    # Stub _PODMAN_CMD as a function that records `secret rm <name>`.
    script = textwrap.dedent(
        f"""\
        set -uo pipefail
        podman() {{
          if [[ "$1" == "secret" && "$2" == "rm" ]]; then echo "$3" >> "{calls}"; fi
        }}
        _PODMAN_CMD="podman"
        """
    ) + body + "\n"
    sp = tmp_path / "run.sh"
    sp.write_text(script, encoding="utf-8")
    proc = subprocess.run([BASH, str(sp)], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    removed = calls.read_text(encoding="utf-8").split() if calls.exists() else []
    for name in OBSOLETE_SECRET_NAMES:
        assert name in removed, f"uninstall did not remove secret {name}; got {removed!r}"
