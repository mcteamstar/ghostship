"""Unit tests for bin/lib/caddy_install.py (installer Caddy config generator).

Note: tests/unit/test_caddy.py already covers transport/caddy.py (the
runtime Caddy portal helper). This file covers bin/lib/caddy_install.py, the
installer module that generates initial-config.json.

Tests run without a live Caddy process or any network access.

Coverage:
(a) TLS mode 'off' sets automatic_https.disable=True.
(b) With API key, routes include a 401 handler.
(c) Without API key, no 401 handler present.
(d) 'acme' mode includes the ACME domain in the TLS policy.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bin.lib.caddy_install import CaddyConfig, generate_caddy_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _doc(**kwargs) -> dict:
    """Return a generated caddy config dict for the given overrides."""
    config = CaddyConfig(**kwargs)
    return generate_caddy_config(config)


def _routes(doc: dict) -> list[dict]:
    return doc["apps"]["http"]["servers"]["ga-main"]["routes"]


def _tls(doc: dict) -> dict:
    return doc["apps"].get("tls", {})


def _route_ids(doc: dict) -> list[str]:
    return [r.get("@id", "") for r in _routes(doc)]


def _find_route(doc: dict, route_id: str) -> dict | None:
    for r in _routes(doc):
        if r.get("@id") == route_id:
            return r
    return None


# ---------------------------------------------------------------------------
# (a) TLS mode 'off' disables automatic_https
# ---------------------------------------------------------------------------

class TestTLSModeOff:
    def test_automatic_https_disabled(self) -> None:
        doc = _doc(tls_mode="off")
        server = doc["apps"]["http"]["servers"]["ga-main"]
        assert server.get("automatic_https", {}).get("disable") is True

    def test_tls_stanza_empty(self) -> None:
        doc = _doc(tls_mode="off")
        assert _tls(doc) == {}


# ---------------------------------------------------------------------------
# TLS mode 'internal'
# ---------------------------------------------------------------------------

class TestTLSModeInternal:
    def test_no_automatic_https_key(self) -> None:
        doc = _doc(tls_mode="internal")
        server = doc["apps"]["http"]["servers"]["ga-main"]
        assert "automatic_https" not in server

    def test_internal_issuer(self) -> None:
        doc = _doc(tls_mode="internal")
        policies = _tls(doc)["automation"]["policies"]
        issuers = [i for p in policies for i in p.get("issuers", [])]
        assert any(i.get("module") == "internal" for i in issuers)


# ---------------------------------------------------------------------------
# TLS mode 'tailscale'
# ---------------------------------------------------------------------------

class TestTLSModeTailscale:
    def test_tailscale_get_certificate(self) -> None:
        doc = _doc(tls_mode="tailscale")
        policies = _tls(doc)["automation"]["policies"]
        certs = [c for p in policies for c in p.get("get_certificate", [])]
        assert any(c.get("via") == "tailscale" for c in certs)

    def test_no_automatic_https_key(self) -> None:
        doc = _doc(tls_mode="tailscale")
        server = doc["apps"]["http"]["servers"]["ga-main"]
        assert "automatic_https" not in server


# ---------------------------------------------------------------------------
# (d) TLS mode 'acme' includes domain in TLS policy
# ---------------------------------------------------------------------------

class TestTLSModeAcme:
    def test_acme_domain_in_subjects(self) -> None:
        doc = _doc(tls_mode="acme", acme_domain="example.com")
        policies = _tls(doc)["automation"]["policies"]
        subjects = [s for p in policies for s in p.get("subjects", [])]
        assert "example.com" in subjects

    def test_acme_issuer_module(self) -> None:
        doc = _doc(tls_mode="acme", acme_domain="example.com")
        policies = _tls(doc)["automation"]["policies"]
        issuers = [i for p in policies for i in p.get("issuers", [])]
        assert any(i.get("module") == "acme" for i in issuers)


# ---------------------------------------------------------------------------
# (b) With API key — 401 handler present
# ---------------------------------------------------------------------------

class TestWithApiKey:
    def test_reject_route_present(self) -> None:
        doc = _doc(ga_api_key="mysecret")
        assert "ga-mcp-files-reject" in _route_ids(doc)

    def test_reject_route_returns_401(self) -> None:
        doc = _doc(ga_api_key="mysecret")
        route = _find_route(doc, "ga-mcp-files-reject")
        assert route is not None
        status = route["handle"][0]["status_code"]
        assert status == 401

    def test_mcp_route_bearer_gated(self) -> None:
        doc = _doc(ga_api_key="mysecret")
        route = _find_route(doc, "ga-transport-mcp")
        assert route is not None
        match = route["match"][0]
        # Must have a header match (bearer gate)
        assert "header" in match
        assert "Authorization" in match["header"]

    def test_files_presigned_route_present(self) -> None:
        doc = _doc(ga_api_key="mysecret")
        assert "ga-transport-files-presigned" in _route_ids(doc)

    def test_radar_route_has_handle_response(self) -> None:
        """Session-gated radar route uses reverse_proxy handle_response."""
        doc = _doc(ga_api_key="mysecret")
        route = _find_route(doc, "ga-radar")
        assert route is not None
        # First handler must be a reverse_proxy with handle_response
        handler = route["handle"][0]
        assert handler.get("handler") == "reverse_proxy"
        assert "handle_response" in handler


    def test_crew_dashboard_route_bearer_gated(self) -> None:
        doc = _doc(ga_api_key="mysecret")
        route = _find_route(doc, "ga-transport-crew-dashboard")
        assert route is not None
        match = route["match"][0]
        assert match["path"] == ["/crews/*/dashboard"]
        assert sorted(match["method"]) == ["DELETE", "POST"]
        assert "Authorization" in match["header"]
        assert route["handle"][0]["upstreams"] == [{"dial": "ga-transport:64057"}]

    def test_crew_dashboard_unauthed_hits_401(self) -> None:
        """Requests without the bearer fall through to the 401 reject route."""
        doc = _doc(ga_api_key="mysecret")
        ids = _route_ids(doc)
        reject = _find_route(doc, "ga-mcp-files-reject")
        assert "/crews/*/dashboard" in reject["match"][0]["path"]
        assert ids.index("ga-transport-crew-dashboard") < ids.index("ga-mcp-files-reject")


class TestAdminSocket:
    def test_admin_api_uses_owner_only_unix_socket(self) -> None:
        doc = _doc()
        assert doc["admin"]["listen"] == "unix//run/ga-portal-admin/admin.sock|0600"
        assert "2019" not in doc["admin"]["listen"]


# ---------------------------------------------------------------------------
# (c) Without API key — no 401 handler present
# ---------------------------------------------------------------------------

class TestWithoutApiKey:
    def test_no_reject_route(self) -> None:
        doc = _doc(ga_api_key="")
        assert "ga-mcp-files-reject" not in _route_ids(doc)

    def test_mcp_route_passthrough(self) -> None:
        doc = _doc(ga_api_key="")
        route = _find_route(doc, "ga-transport-mcp")
        assert route is not None
        match = route["match"][0]
        # No bearer header gate
        assert "header" not in match

    def test_mcp_route_keeps_transport_upstream(self) -> None:
        doc = _doc(ga_api_key="")
        route = _find_route(doc, "ga-transport-mcp")
        assert route is not None
        assert route["handle"][0]["upstreams"] == [
            {"dial": "ga-transport:64057"}
        ]

    def test_no_files_presigned_route(self) -> None:
        doc = _doc(ga_api_key="")
        assert "ga-transport-files-presigned" not in _route_ids(doc)

    def test_crew_dashboard_route_passthrough(self) -> None:
        doc = _doc(ga_api_key="")
        route = _find_route(doc, "ga-transport-crew-dashboard")
        assert route is not None
        match = route["match"][0]
        assert match["path"] == ["/crews/*/dashboard"]
        assert sorted(match["method"]) == ["DELETE", "POST"]
        assert "header" not in match

    def test_radar_route_is_passthrough(self) -> None:
        doc = _doc(ga_api_key="")
        route = _find_route(doc, "ga-radar")
        assert route is not None
        # Passthrough: single handler, no handle_response
        assert len(route["handle"]) == 1
        handler = route["handle"][0]
        assert handler.get("handler") == "reverse_proxy"
        assert "handle_response" not in handler


# ---------------------------------------------------------------------------
# Misc route always present
# ---------------------------------------------------------------------------

class TestMiscRoute:
    def test_misc_route_present(self) -> None:
        doc = _doc()
        assert "ga-transport-misc" in _route_ids(doc)

    def test_misc_route_matches_health_and_dashboard(self) -> None:
        doc = _doc()
        route = _find_route(doc, "ga-transport-misc")
        assert route is not None
        paths = route["match"][0]["path"]
        assert "/health" in paths
        assert "/dashboard/*" in paths

    def test_misc_route_is_last(self) -> None:
        doc = _doc()
        ids = _route_ids(doc)
        assert ids[-1] == "ga-transport-misc"


# ---------------------------------------------------------------------------
# Portal-token header on upstreams
# ---------------------------------------------------------------------------

class TestPortalTokenHeader:
    def test_mcp_route_injects_transport_token(self) -> None:
        doc = _doc(ga_api_key="")
        route = _find_route(doc, "ga-transport-mcp")
        handler = route["handle"][0]
        token_header = handler["headers"]["request"]["set"].get(
            "X-Transport-Token", []
        )
        assert any("ga-transport-secret" in t for t in token_header)


# ---------------------------------------------------------------------------
# JSON serialisability
# ---------------------------------------------------------------------------

class TestJSONSerialisation:
    def test_output_is_json_serialisable(self) -> None:
        doc = _doc(tls_mode="acme", acme_domain="example.com", ga_api_key="key")
        # Must not raise
        json.dumps(doc, indent=2)
