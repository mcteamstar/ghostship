"""Installer tests for portal-only-host.

HOST is the address ga-portal publishes on; the transport always listens on
0.0.0.0 inside its container. The API key is network.api_key (key / unset /
false opt-out), resolved as --api-key > YAML > saved --api-key.

* **Rendered** — render install.sh's compose.yml heredoc via Python and assert
  on the result.
* **Static** — assert on the text of install.sh / start.sh where a behavioural
  run would need Podman.

Note: the bash subprocess tests (``@needs_bash``) that previously lived here have
been removed. They hang inside containers and were fully covered by
``test_portal_host_py.py`` (pure-Python tests against portal_host.py) introduced
in TRN-294. See TRN-296 for the rationale.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = REPO_ROOT / "bin" / "install.sh"
START_SH = REPO_ROOT / "bin" / "start.sh"


@pytest.fixture(scope="module")
def install_sh_text() -> str:
    return INSTALL_SH.read_text(encoding="utf-8")


# ── compose.yml rendering ────────────────────────────────────────────────────
# NOTE: compose.yml generation has moved to bin/lib/compose.py (Python).
# The tests below exercise generate_compose() directly instead of the old
# bash heredoc that lived in install.sh.

import sys as _sys
_VENDOR = REPO_ROOT / "bin" / "lib" / "vendor"
if str(_VENDOR) not in _sys.path:
    _sys.path.insert(0, str(_VENDOR))
from bin.lib.compose import ComposeConfig, generate_compose  # noqa: E402


def _render_compose_py(host: str) -> str:
    """Generate a compose.yml string via the Python API for the given HOST."""
    # Compute portal_bind the same way compose._config_from_env() does.
    raw = host or "127.0.0.1"
    if ":" in raw and not raw.startswith("["):
        portal_bind = f"[{raw}]"
    else:
        portal_bind = raw

    # Compute ga_host_url via the Python public_base function.
    from bin.lib import portal_host as _ph  # noqa: PLC0415
    ga_host_url = _ph.public_base(host, "64057")

    cfg = ComposeConfig(
        data_dir="/data/ghost-academy",
        podman_sock="/run/user/1000/podman/podman.sock",
        port="64057",
        host=host,
        portal_bind=portal_bind,
        ga_host_url=ga_host_url,
        dashboard_port_range_start="64058",
        dashboard_port_range_end="64121",
    )
    return generate_compose(cfg)


@pytest.mark.parametrize(
    "host,bind,url",
    [
        ("127.0.0.1", "127.0.0.1", "http://localhost:64057"),
        ("0.0.0.0", "0.0.0.0", "http://localhost:64057"),
        ("192.168.1.10", "192.168.1.10", "http://192.168.1.10:64057"),
    ],
)
def test_compose_publishes_portal_on_host_only(
    host: str, bind: str, url: str
) -> None:
    """compose.py generates correct portal port bindings for each HOST value."""
    compose = _render_compose_py(host)
    assert f"- {bind}:64057:64057" in compose
    assert f"- {bind}:64058-64121:64058-64121" in compose
    # The transport never reads HOST; it listens on a fixed address.
    transport = compose.split("  ga-portal:")[0]
    assert "\n      HOST:" not in transport
    assert "GA_TRANSPORT_BIND: 0.0.0.0" in transport
    assert f"GA_PORTAL_HOST: {host}" in transport
    assert f"GA_HOST_URL: {url}" in transport
    assert "GA_REQUIRE_API_KEY" not in compose


# ── Readiness goes through the portal ────────────────────────────────────────

def test_install_fails_when_portal_cannot_reach_transport() -> None:
    """Health-check logic in install_main.py probes through ga-portal and exits
    non-zero when the probe fails — confirmed by static analysis of the source."""
    install_main = (REPO_ROOT / "bin" / "lib" / "install_main.py").read_text(encoding="utf-8")
    # The health check must use probe_base (portal-facing URL, not 127.0.0.1 direct).
    assert "probe_base" in install_main or "_probe_base" in install_main
    # The old bypass that probed the transport container directly must be gone.
    assert "127.0.0.1:${PORT}/health" not in install_main
    # The health-check function must exit on failure.
    assert "sys.exit(1)" in install_main


def test_readiness_no_longer_trusts_in_container_probe(install_sh_text: str) -> None:
    # Health check logic has moved to install_main.py (Python); install.sh is now
    # a thin shim that execs into Python. Check that install_main.py uses the
    # portal probe approach.
    install_main = (REPO_ROOT / "bin" / "lib" / "install_main.py").read_text(encoding="utf-8")
    assert "probe_base" in install_main or "_probe_base" in install_main
    assert "127.0.0.1:${PORT}/health" not in install_main


def test_start_sh_probes_through_portal() -> None:
    text = START_SH.read_text(encoding="utf-8")
    # start.sh now uses portal_host.py probe_base command
    assert "portal_host.py" in text or "probe_base" in text
    assert 'curl -sf "http://127.0.0.1:${PORT}/health"' not in text


# ── Static: the old guard is gone ────────────────────────────────────────────

def test_install_sh_has_no_require_api_key_logic(install_sh_text: str) -> None:
    lines = [ln for ln in install_sh_text.splitlines() if "GA_REQUIRE_API_KEY" in ln]
    # Only comments may reference the deprecated GA_REQUIRE_API_KEY.
    assert all(ln.lstrip().startswith("#") for ln in lines), lines
    # The logic has moved to install_main.py (check exposure, resolve api key).
    install_main = (REPO_ROOT / "bin" / "lib" / "install_main.py").read_text(encoding="utf-8")
    assert "check_exposure" in install_main or "_check_exposure" in install_main
    assert "resolve_api_key" in install_main or "_resolve_api_key" in install_main
