"""Installer tests for portal-only-host.

HOST is the address ga-portal publishes on; the transport always listens on
0.0.0.0 inside its container. The API key is network.api_key (key / unset /
false opt-out), resolved as --api-key > YAML > saved --api-key.

* **Behavioural** — source ``bin/lib/portal_host.sh`` in a real ``bash``
  subprocess and drive its functions (skipped when bash is unavailable).
* **Rendered** — render install.sh's compose.yml heredoc with bash and assert
  on the result.
* **Static** — assert on the text of install.sh / start.sh where a behavioural
  run would need Podman.
"""

from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = REPO_ROOT / "bin" / "install.sh"
START_SH = REPO_ROOT / "bin" / "start.sh"
PORTAL_LIB = REPO_ROOT / "bin" / "lib" / "portal_host.sh"

BASH = shutil.which("bash")
needs_bash = pytest.mark.skipif(not BASH, reason="bash not available")


def _run(script: str, tmp_path: Path) -> subprocess.CompletedProcess:
    sp = tmp_path / "run.sh"
    sp.write_text(
        f'set -euo pipefail\nsource "{PORTAL_LIB}"\n' + textwrap.dedent(script),
        encoding="utf-8",
    )
    return subprocess.run([BASH, str(sp)], capture_output=True, text=True, timeout=30)


@pytest.fixture(scope="module")
def install_sh_text() -> str:
    return INSTALL_SH.read_text(encoding="utf-8")


# ── Address helpers ──────────────────────────────────────────────────────────

@needs_bash
@pytest.mark.parametrize(
    "host,want",
    [
        ("", "http://localhost:64057"),
        ("127.0.0.1", "http://localhost:64057"),
        ("::1", "http://localhost:64057"),
        ("0.0.0.0", "http://localhost:64057"),
        ("::", "http://localhost:64057"),
        ("192.168.1.10", "http://192.168.1.10:64057"),
        ("2001:db8::1", "http://[2001:db8::1]:64057"),
    ],
)
def test_public_base_follows_host(tmp_path: Path, host: str, want: str) -> None:
    proc = _run(f'portal_public_base "{host}" 64057', tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == want


@needs_bash
@pytest.mark.parametrize(
    "host,scheme,want",
    [
        ("127.0.0.1", "http", "http://127.0.0.1:64057"),
        ("0.0.0.0", "http", "http://127.0.0.1:64057"),
        ("", "http", "http://127.0.0.1:64057"),
        ("192.168.1.10", "http", "http://192.168.1.10:64057"),
        ("::1", "https", "https://[::1]:64057"),
    ],
)
def test_probe_base(tmp_path: Path, host: str, scheme: str, want: str) -> None:
    proc = _run(f'portal_probe_base "{host}" 64057 {scheme}', tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == want


# ── API key resolution ───────────────────────────────────────────────────────

def _resolve(
    tmp_path: Path,
    *,
    flag: str | None = None,
    yaml_key: str = "",
    yaml_disabled: str = "",
    yaml_source: str = "",
    deprecated_off: str = "",
    saved_flag: str | None = None,
    legacy_effective: str | None = None,
) -> tuple[subprocess.CompletedProcess, Path]:
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    if saved_flag is not None:
        (data / "ga-api-key.flag").write_text(saved_flag, encoding="utf-8")
    if legacy_effective is not None:
        (data / "ga-api-key").write_text(legacy_effective, encoding="utf-8")
    passed = "1" if flag is not None else "0"
    proc = _run(
        f"""\
        DATA_DIR="{data}"
        API_KEY_FLAG_PASSED={passed}
        _FLAG_API_KEY="{flag or ''}"
        GA_API_KEY="{yaml_key}"
        GA_API_KEY_DISABLED="{yaml_disabled}"
        GA_API_KEY_SOURCE="{yaml_source}"
        GA_API_KEY_DEPRECATED_OFF="{deprecated_off}"
        portal_resolve_api_key
        echo "KEY=${{GA_API_KEY}}"
        echo "DISABLED=${{GA_API_KEY_DISABLED}}"
        """,
        tmp_path,
    )
    return proc, data


def _effective(data: Path) -> str | None:
    path = data / "ga-api-key"
    return path.read_text(encoding="utf-8") if path.exists() else None


@needs_bash
def test_yaml_key_wins_over_stale_saved_key(tmp_path: Path) -> None:
    proc, data = _resolve(tmp_path, yaml_key="new-key", yaml_source="yaml", saved_flag="old-key")
    assert proc.returncode == 0, proc.stderr
    assert "KEY=new-key" in proc.stdout
    assert _effective(data) == "new-key"


@needs_bash
def test_yaml_opt_out_wins_over_saved_key(tmp_path: Path) -> None:
    proc, data = _resolve(tmp_path, yaml_disabled="true", yaml_source="yaml", saved_flag="old-key")
    assert "KEY=\n" in proc.stdout and "DISABLED=true" in proc.stdout
    assert _effective(data) is None


@needs_bash
def test_flag_wins_over_yaml(tmp_path: Path) -> None:
    proc, data = _resolve(tmp_path, flag="flag-key", yaml_key="yaml-key", yaml_source="yaml")
    assert "KEY=flag-key" in proc.stdout
    assert (data / "ga-api-key.flag").read_text(encoding="utf-8") == "flag-key"
    assert _effective(data) == "flag-key"


@needs_bash
def test_empty_flag_clears_saved_key_and_falls_through_to_yaml(tmp_path: Path) -> None:
    proc, data = _resolve(
        tmp_path, flag="", yaml_key="yaml-key", yaml_source="yaml", saved_flag="old-key"
    )
    assert "KEY=yaml-key" in proc.stdout
    assert (data / "ga-api-key.flag").read_text(encoding="utf-8") == ""


@needs_bash
def test_saved_key_used_when_nothing_else_set(tmp_path: Path) -> None:
    proc, data = _resolve(tmp_path, saved_flag="old-key")
    assert "KEY=old-key" in proc.stdout
    assert _effective(data) == "old-key"


@needs_bash
def test_deprecated_off_is_opt_out_when_no_key(tmp_path: Path) -> None:
    proc, data = _resolve(tmp_path, deprecated_off="true")
    assert "DISABLED=true" in proc.stdout
    assert _effective(data) is None


@needs_bash
def test_deprecated_off_never_disables_saved_key(tmp_path: Path) -> None:
    proc, _ = _resolve(tmp_path, deprecated_off="true", saved_flag="old-key")
    assert "KEY=old-key" in proc.stdout
    assert "DISABLED=\n" in proc.stdout


@needs_bash
def test_legacy_key_file_migrated_once(tmp_path: Path) -> None:
    # Pre-change installs only ever wrote ga-api-key via --api-key.
    proc, data = _resolve(tmp_path, legacy_effective="legacy-key")
    assert "KEY=legacy-key" in proc.stdout
    assert (data / "ga-api-key.flag").read_text(encoding="utf-8") == "legacy-key"
    # A later YAML-only key lands in ga-api-key but must never become a flag key.
    proc, data = _resolve(tmp_path, flag="", yaml_key="yaml-key", yaml_source="yaml")
    assert _effective(data) == "yaml-key"
    proc, data = _resolve(tmp_path)  # YAML key removed, no flag
    assert "KEY=\n" in proc.stdout
    assert _effective(data) is None


# ── Exposure check ───────────────────────────────────────────────────────────

def _check(tmp_path: Path, host: str, key: str = "", disabled: str = ""):
    return _run(
        f"""\
        GA_API_KEY="{key}"
        GA_API_KEY_DISABLED="{disabled}"
        portal_check_exposure "{host}" 64057
        """,
        tmp_path,
    )


@needs_bash
@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10"])
def test_non_loopback_without_key_aborts(tmp_path: Path, host: str) -> None:
    proc = _check(tmp_path, host)
    assert proc.returncode == 1
    assert f"{host}:64057" in proc.stderr
    assert "WARNING" in proc.stderr
    assert "--api-key" in proc.stderr
    assert "network.host: 127.0.0.1" in proc.stderr
    assert "network.api_key: false" in proc.stderr


@needs_bash
@pytest.mark.parametrize("host", ["", "127.0.0.1", "::1", "localhost"])
def test_loopback_without_key_passes_silently(tmp_path: Path, host: str) -> None:
    proc = _check(tmp_path, host)
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == ""


@needs_bash
def test_opt_out_passes_with_warning(tmp_path: Path) -> None:
    proc = _check(tmp_path, "0.0.0.0", disabled="true")
    assert proc.returncode == 0, proc.stderr
    assert "explicitly disabled" in proc.stderr


@needs_bash
def test_key_on_non_loopback_passes_silently(tmp_path: Path) -> None:
    proc = _check(tmp_path, "0.0.0.0", key="s3cret")
    assert proc.returncode == 0
    assert proc.stderr == ""


# ── Legacy bind notice ───────────────────────────────────────────────────────

@needs_bash
def test_notice_when_previous_compose_published_on_all_interfaces(tmp_path: Path) -> None:
    compose = tmp_path / "compose.yml"
    compose.write_text('    ports:\n      - "0.0.0.0:64057:64057"\n', encoding="utf-8")
    proc = _run(f'portal_legacy_bind_notice "{compose}" 127.0.0.1 64057', tmp_path)
    assert proc.returncode == 0
    assert "network.host" in proc.stderr


@needs_bash
@pytest.mark.parametrize(
    "existing,host",
    [
        (None, "127.0.0.1"),  # fresh install
        ('      - "127.0.0.1:64057:64057"\n', "127.0.0.1"),  # already loopback
        ('      - "0.0.0.0:64057:64057"\n', "0.0.0.0"),  # still wildcard
    ],
)
def test_no_notice_otherwise(tmp_path: Path, existing: str | None, host: str) -> None:
    compose = tmp_path / "compose.yml"
    if existing is not None:
        compose.write_text(existing, encoding="utf-8")
    proc = _run(f'portal_legacy_bind_notice "{compose}" {host} 64057', tmp_path)
    assert proc.returncode == 0
    assert proc.stderr == ""


# ── compose.yml rendering ────────────────────────────────────────────────────

def _render_compose(install_sh_text: str, tmp_path: Path, host: str) -> str:
    start = install_sh_text.index('cat > "${DATA_DIR}/compose.yml" <<COMPOSE_EOF')
    end = install_sh_text.index("\nCOMPOSE_EOF\n", start) + len("\nCOMPOSE_EOF\n")
    block = install_sh_text[start:end]
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    proc = _run(
        f"""\
        set +u
        DATA_DIR="{data}"
        HOST="{host}"
        PORT=64057
        _DASHBOARD_PORT_START=64058
        _DASHBOARD_PORT_END=64121
        _PORTAL_BIND="$(portal_addr "$HOST")"
        GA_HOST_URL="$(portal_public_base "$HOST" "$PORT")"
        """
        + block,
        tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    return (data / "compose.yml").read_text(encoding="utf-8")


@needs_bash
@pytest.mark.parametrize(
    "host,bind,url",
    [
        ("127.0.0.1", "127.0.0.1", "http://localhost:64057"),
        ("0.0.0.0", "0.0.0.0", "http://localhost:64057"),
        ("192.168.1.10", "192.168.1.10", "http://192.168.1.10:64057"),
    ],
)
def test_compose_publishes_portal_on_host_only(
    install_sh_text: str, tmp_path: Path, host: str, bind: str, url: str
) -> None:
    compose = _render_compose(install_sh_text, tmp_path, host)
    assert f'- "{bind}:64057:64057"' in compose
    assert f'- "{bind}:64058-64121:64058-64121"' in compose
    # The transport never reads HOST; it listens on a fixed address.
    transport = compose.split("  ga-portal:")[0]
    assert "\n      HOST:" not in transport
    assert 'GA_TRANSPORT_BIND: "0.0.0.0"' in transport
    assert f'GA_PORTAL_HOST: "{host}"' in transport
    assert f'GA_HOST_URL: "{url}"' in transport
    assert "GA_REQUIRE_API_KEY" not in compose


# ── Readiness goes through the portal ────────────────────────────────────────

def _extract_readiness(install_sh_text: str) -> str:
    start = install_sh_text.index('_caddy_scheme="http"')
    end = install_sh_text.index("  exit 1\nfi\n", start) + len("  exit 1\nfi\n")
    return install_sh_text[start:end]


@needs_bash
def test_install_fails_when_portal_cannot_reach_transport(
    install_sh_text: str, tmp_path: Path
) -> None:
    """Caddy answers 502 but the transport is healthy inside its container: the
    install must fail, naming the portal-to-transport path."""
    podman = tmp_path / "podman-stub"
    podman.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")  # exec probe passes
    podman.chmod(0o755)
    proc = _run(
        f"""\
        curl() {{ return 22; }}   # every request through the portal fails
        HOST=127.0.0.1
        PORT=64057
        GA_PORTAL_TLS_MODE=off
        _PODMAN_CMD="{podman}"
        _max_wait=1
        _interval=1
        _ready=0
        """
        + _extract_readiness(install_sh_text),
        tmp_path,
    )
    assert proc.returncode == 1
    assert "portal-to-transport" in proc.stderr
    assert "http://127.0.0.1:64057/health" in proc.stderr


def test_readiness_no_longer_trusts_in_container_probe(install_sh_text: str) -> None:
    block = _extract_readiness(install_sh_text)
    assert "portal_probe_base" in block
    # The container-internal probe targets the fixed internal port, not PORT.
    assert "127.0.0.1:${PORT}/health" not in block
    assert "127.0.0.1:64057/health" in block


def test_start_sh_probes_through_portal() -> None:
    text = START_SH.read_text(encoding="utf-8")
    assert "portal_probe_base" in text
    assert "GA_PORTAL_HOST" in text
    assert 'curl -sf "http://127.0.0.1:${PORT}/health"' not in text


# ── Static: the old guard is gone ────────────────────────────────────────────

def test_install_sh_has_no_require_api_key_logic(install_sh_text: str) -> None:
    lines = [ln for ln in install_sh_text.splitlines() if "GA_REQUIRE_API_KEY" in ln]
    # Only the explanatory comment about the deprecation remains.
    assert all(ln.lstrip().startswith("#") for ln in lines), lines
    assert "portal_check_exposure" in install_sh_text
    assert "portal_resolve_api_key" in install_sh_text
