"""Unit tests for bin/lib/compose.py.

Tests run without Podman or any live container infrastructure.

Coverage:
(a) Minimal config produces all three services.
(b) With GA_API_KEY set the secret mount appears.
(c) Without GA_API_KEY no ga-api-key secret is declared.
(d) Missing required field raises ValueError.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the vendored PyYAML is on the path for the import
REPO_ROOT = Path(__file__).resolve().parents[2]
VENDOR = REPO_ROOT / "bin" / "lib" / "vendor"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

from bin.lib.compose import ComposeConfig, generate_compose  # noqa: E402

import yaml  # noqa: E402 (vendored)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_config(**overrides) -> ComposeConfig:
    """Return a minimal valid ComposeConfig with optional overrides."""
    base = dict(
        data_dir="/data/ghost-academy",
        podman_sock="/run/user/1000/podman/podman.sock",
        port="64057",
        host="127.0.0.1",
        portal_bind="127.0.0.1",
        ga_host_url="http://localhost:64057",
        dashboard_port_range_start="64058",
        dashboard_port_range_end="64121",
    )
    base.update(overrides)
    return ComposeConfig(**base)


def _parsed(config: ComposeConfig) -> dict:
    """Return the generated YAML parsed back to a dict."""
    return yaml.safe_load(generate_compose(config))


# ---------------------------------------------------------------------------
# (a) Minimal config — three services, both networks
# ---------------------------------------------------------------------------

class TestMinimalConfig:
    def test_all_three_services_present(self) -> None:
        doc = _parsed(_minimal_config())
        services = doc["services"]
        assert "ga-transport" in services
        assert "ga-portal" in services
        assert "ga-radar" in services

    def test_both_networks_declared(self) -> None:
        doc = _parsed(_minimal_config())
        networks = doc.get("networks", {})
        assert "ga-portside" in networks
        assert "ga-starboard" in networks

    def test_transport_on_both_networks(self) -> None:
        doc = _parsed(_minimal_config())
        transport_nets = doc["services"]["ga-transport"]["networks"]
        assert "ga-portside" in transport_nets
        assert "ga-starboard" in transport_nets

    def test_radar_on_portside_only(self) -> None:
        doc = _parsed(_minimal_config())
        radar_nets = doc["services"]["ga-radar"]["networks"]
        assert "ga-portside" in radar_nets
        assert "ga-starboard" not in radar_nets

    def test_portal_on_portside_only(self) -> None:
        doc = _parsed(_minimal_config())
        portal_nets = doc["services"]["ga-portal"]["networks"]
        assert "ga-portside" in portal_nets
        assert "ga-starboard" not in portal_nets

    def test_transport_bearer_secret_present(self) -> None:
        doc = _parsed(_minimal_config())
        assert "ga-transport-secret" in doc["services"]["ga-transport"]["secrets"]
        assert "ga-transport-secret" in doc["secrets"]

    def test_ga_portal_data_volume_present(self) -> None:
        doc = _parsed(_minimal_config())
        assert "ga-portal-data" in doc["volumes"]

    def test_service_order(self) -> None:
        """Service insertion order must be ga-transport, ga-radar, ga-portal."""
        doc = _parsed(_minimal_config())
        keys = list(doc["services"].keys())
        assert keys == ["ga-transport", "ga-radar", "ga-portal"]


# ---------------------------------------------------------------------------
# (b) With GA_API_KEY — secret mount appears
# ---------------------------------------------------------------------------

class TestWithApiKey:
    def test_api_key_secret_in_transport(self) -> None:
        doc = _parsed(_minimal_config(ga_api_key="test-secret-key"))
        assert "ga-api-key" in doc["services"]["ga-transport"]["secrets"]

    def test_api_key_secret_in_portal(self) -> None:
        doc = _parsed(_minimal_config(ga_api_key="test-secret-key"))
        assert "ga-api-key" in doc["services"]["ga-portal"]["secrets"]

    def test_api_key_in_top_level_secrets(self) -> None:
        doc = _parsed(_minimal_config(ga_api_key="test-secret-key"))
        assert "ga-api-key" in doc["secrets"]
        assert doc["secrets"]["ga-api-key"] == {"external": True}


# ---------------------------------------------------------------------------
# (c) Without GA_API_KEY — no ga-api-key secret declared
# ---------------------------------------------------------------------------

class TestWithoutApiKey:
    def test_no_api_key_secret_in_transport(self) -> None:
        doc = _parsed(_minimal_config(ga_api_key=""))
        assert "ga-api-key" not in doc["services"]["ga-transport"]["secrets"]

    def test_no_api_key_secret_in_portal(self) -> None:
        doc = _parsed(_minimal_config(ga_api_key=""))
        assert "ga-api-key" not in doc["services"]["ga-portal"]["secrets"]

    def test_no_api_key_in_top_level_secrets(self) -> None:
        doc = _parsed(_minimal_config(ga_api_key=""))
        assert "ga-api-key" not in doc["secrets"]


# ---------------------------------------------------------------------------
# (d) Missing required field raises ValueError
# ---------------------------------------------------------------------------

class TestRequiredFields:
    def test_empty_data_dir_raises(self) -> None:
        with pytest.raises(ValueError, match="data_dir"):
            ComposeConfig(data_dir="", podman_sock="/run/user/1000/podman/podman.sock")

    def test_empty_podman_sock_raises(self) -> None:
        with pytest.raises(ValueError, match="podman_sock"):
            ComposeConfig(data_dir="/data", podman_sock="")


# ---------------------------------------------------------------------------
# Conditional sections
# ---------------------------------------------------------------------------

class TestConditionalSections:
    def test_orders_dir_bind_mount_present(self) -> None:
        doc = _parsed(_minimal_config(ga_orders_dir="/host/orders"))
        volumes = doc["services"]["ga-transport"]["volumes"]
        assert "/host/orders:/mnt/orders:ro" in volumes

    def test_orders_dir_bind_mount_absent(self) -> None:
        doc = _parsed(_minimal_config(ga_orders_dir=""))
        volumes = doc["services"]["ga-transport"]["volumes"]
        assert all(":mnt/orders" not in v for v in volumes)

    def test_tls_bind_mount_present(self) -> None:
        doc = _parsed(_minimal_config(
            ga_tls_certfile="/certs/server.crt",
            ga_tls_keyfile="/certs/server.key",
        ))
        volumes = doc["services"]["ga-transport"]["volumes"]
        assert "/certs:/mnt/tls:ro" in volumes

    def test_tls_bind_mount_absent(self) -> None:
        doc = _parsed(_minimal_config())
        volumes = doc["services"]["ga-transport"]["volumes"]
        assert all(":mnt/tls" not in v for v in volumes)

    def test_tls_env_vars_set_when_certfile_provided(self) -> None:
        doc = _parsed(_minimal_config(
            ga_tls_certfile="/certs/server.crt",
            ga_tls_keyfile="/certs/server.key",
        ))
        env = doc["services"]["ga-transport"]["environment"]
        assert env["GA_TLS_CERTFILE"] == "/mnt/tls/server.crt"
        assert env["GA_TLS_KEYFILE"] == "/mnt/tls/server.key"

    def test_tls_env_vars_empty_without_certfile(self) -> None:
        doc = _parsed(_minimal_config())
        env = doc["services"]["ga-transport"]["environment"]
        assert env["GA_TLS_CERTFILE"] == ""
        assert env["GA_TLS_KEYFILE"] == ""

    def test_orders_dir_env_var_set(self) -> None:
        doc = _parsed(_minimal_config(ga_orders_dir="/host/orders"))
        env = doc["services"]["ga-transport"]["environment"]
        assert env["GA_ORDERS_DIR"] == "/mnt/orders"

    def test_orders_dir_env_var_empty(self) -> None:
        doc = _parsed(_minimal_config())
        env = doc["services"]["ga-transport"]["environment"]
        assert env["GA_ORDERS_DIR"] == ""


# ---------------------------------------------------------------------------
# Portal port range
# ---------------------------------------------------------------------------

class TestPortalPorts:
    def test_main_port_binding(self) -> None:
        doc = _parsed(_minimal_config(
            host="127.0.0.1",
            portal_bind="127.0.0.1",
            port="64057",
            dashboard_port_range_start="64058",
            dashboard_port_range_end="64121",
        ))
        ports = doc["services"]["ga-portal"]["ports"]
        assert "127.0.0.1:64057:64057" in ports

    def test_dashboard_port_range_binding(self) -> None:
        doc = _parsed(_minimal_config(
            portal_bind="127.0.0.1",
            dashboard_port_range_start="64058",
            dashboard_port_range_end="64121",
        ))
        ports = doc["services"]["ga-portal"]["ports"]
        assert "127.0.0.1:64058-64121:64058-64121" in ports
