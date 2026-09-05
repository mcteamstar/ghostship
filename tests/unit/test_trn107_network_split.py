"""Unit tests for TRN-107 — Portside/Starboard network split and GA_PORTAL_SECRET.

Covers:
  7.1  GA_PORTSIDE_NETWORK / GA_STARBOARD_NETWORK constant values
  7.2  PortalSecretMiddleware: missing header → 401
  7.3  PortalSecretMiddleware: correct header → pass-through
  7.4  PortalSecretMiddleware: wrong header value → 401
  7.5  PortalSecretMiddleware: pass-through when portal_secret is empty
  7.6  _migrate_crew_network: already on ga-starboard → no-op
  7.7  _migrate_crew_network: on ga-net → full migration sequence
  7.8  _migrate_crew_network: gateway not ready after migration → returns False
  7.9  _reconcile_registry: migration failure marks crew stopped, continues
  7.10 _reconcile_registry: best-effort ga-net removal attempted after migration
  7.11 network_connect / network_disconnect / container_networks on PodmanClient
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import MagicMock, Mock, call, patch

from tests.unit.helpers import lifecycle, server


# ── Shared ASGI test helpers (mirrors test_server.py pattern) ─────────────────

class _FakeDownstream:
    """Minimal ASGI downstream that records whether it was reached."""

    def __init__(self) -> None:
        self.called = False

    async def __call__(self, scope, receive, send) -> None:
        self.called = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"OK"})


def _http_scope(headers: list[tuple[bytes, bytes]] | None = None, path: str = "/mcp") -> dict:
    return {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": headers or [],
    }


def _run_asgi(app, scope, body: bytes = b"") -> tuple[int, list, bytes]:
    """Run an ASGI app synchronously; return (status, headers, body)."""
    status = None
    resp_headers: list = []
    resp_body = b""

    async def receive():
        return {"type": "http.request", "body": body}

    async def send(msg):
        nonlocal status, resp_headers, resp_body
        if msg["type"] == "http.response.start":
            status = msg["status"]
            resp_headers = msg.get("headers", [])
        elif msg["type"] == "http.response.body":
            resp_body += msg.get("body", b"")

    asyncio.run(app(scope, receive, send))
    return status, resp_headers, resp_body


# ── 7.1: Constants ────────────────────────────────────────────────────────────

class NetworkConstantTests(unittest.TestCase):
    """GA_PORTSIDE_NETWORK and GA_STARBOARD_NETWORK have the expected values."""

    def test_portside_constant_value(self) -> None:
        self.assertEqual(lifecycle.GA_PORTSIDE_NETWORK, "ga-portside")

    def test_starboard_constant_value(self) -> None:
        self.assertEqual(lifecycle.GA_STARBOARD_NETWORK, "ga-starboard")

    def test_server_portside_constant_value(self) -> None:
        self.assertEqual(server.GA_PORTSIDE_NETWORK, "ga-portside")

    def test_server_starboard_constant_value(self) -> None:
        self.assertEqual(server.GA_STARBOARD_NETWORK, "ga-starboard")


# ── 7.2–7.5: PortalSecretMiddleware ──────────────────────────────────────────

class PortalSecretMiddlewareTests(unittest.TestCase):
    """Tests for PortalSecretMiddleware (TRN-107 outermost gate)."""

    def test_missing_header_returns_401(self) -> None:
        """Request with no X-Portal-Token header → 401."""
        downstream = _FakeDownstream()
        mw = server.PortalSecretMiddleware(downstream, portal_secret="correct-secret")
        scope = _http_scope()  # no headers
        status, headers, body = _run_asgi(mw, scope)
        self.assertEqual(status, 401)
        self.assertFalse(downstream.called)

    def test_correct_header_passes_through(self) -> None:
        """Request with correct X-Portal-Token → forwarded to downstream (200)."""
        downstream = _FakeDownstream()
        secret = "my-portal-secret-abc123"
        mw = server.PortalSecretMiddleware(downstream, portal_secret=secret)
        scope = _http_scope(headers=[(b"x-portal-token", secret.encode())])
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 200)
        self.assertTrue(downstream.called)

    def test_wrong_header_value_returns_401(self) -> None:
        """Request with wrong X-Portal-Token value → 401."""
        downstream = _FakeDownstream()
        mw = server.PortalSecretMiddleware(downstream, portal_secret="correct")
        scope = _http_scope(headers=[(b"x-portal-token", b"wrong")])
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 401)
        self.assertFalse(downstream.called)

    def test_empty_portal_secret_is_pass_through(self) -> None:
        """When portal_secret is empty, middleware is a transparent pass-through."""
        downstream = _FakeDownstream()
        mw = server.PortalSecretMiddleware(downstream, portal_secret="")
        scope = _http_scope()  # no X-Portal-Token header
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 200)
        self.assertTrue(downstream.called)

    def test_non_http_scope_passes_through(self) -> None:
        """Non-HTTP scopes (websocket, lifespan) pass through unchanged."""
        downstream = _FakeDownstream()
        mw = server.PortalSecretMiddleware(downstream, portal_secret="secret")
        scope = {"type": "lifespan"}

        async def _noop(msg=None):
            pass

        async def _run():
            await mw(scope, _noop, _noop)

        asyncio.run(_run())
        self.assertTrue(downstream.called)

    def test_401_response_body_is_unauthorized(self) -> None:
        """Rejected requests return 401 with 'Unauthorized' body."""
        downstream = _FakeDownstream()
        mw = server.PortalSecretMiddleware(downstream, portal_secret="secret")
        scope = _http_scope()
        status, _, body = _run_asgi(mw, scope)
        self.assertEqual(status, 401)
        self.assertEqual(body, b"Unauthorized")


# ── 7.6–7.10: _migrate_crew_network + _reconcile_registry ────────────────────

class MigrateCrewNetworkTests(unittest.TestCase):
    """Tests for _migrate_crew_network (D3 migration algorithm)."""

    def _make_podman(
        self,
        *,
        container_networks: list[str],
        wait_gateway_result: bool = True,
    ) -> MagicMock:
        """Build a mock PodmanClient for migration tests."""
        podman = MagicMock()
        podman.container_networks.return_value = container_networks
        podman.container_stop.return_value = None
        podman.container_start.return_value = None
        podman.network_connect.return_value = None
        podman.network_disconnect.return_value = None
        return podman

    def test_already_on_starboard_is_noop(self) -> None:
        """Container already on ga-starboard — no migration steps called."""
        podman = self._make_podman(container_networks=["ga-starboard"])
        with patch.object(lifecycle, "_wait_gateway", return_value=True):
            result = lifecycle._migrate_crew_network(podman, "alpha", "gs-alpha")
        self.assertTrue(result)
        podman.network_connect.assert_not_called()
        podman.network_disconnect.assert_not_called()
        podman.container_stop.assert_not_called()

    def test_on_ga_net_triggers_full_migration(self) -> None:
        """Container on ga-net → full migration: stop, disconnect, connect, start."""
        podman = self._make_podman(container_networks=["ga-net"])
        with patch.object(lifecycle, "_wait_gateway", return_value=True):
            result = lifecycle._migrate_crew_network(podman, "alpha", "gs-alpha")
        self.assertTrue(result)
        # Step a: connect ga-transport to ga-starboard (idempotent)
        podman.network_connect.assert_any_call("ga-transport", "ga-starboard")
        # Step b: stop container
        podman.container_stop.assert_called_once_with("gs-alpha")
        # Step c: disconnect from ga-net
        podman.network_disconnect.assert_called_once_with("gs-alpha", "ga-net")
        # Step d: connect to ga-starboard
        podman.network_connect.assert_any_call("gs-alpha", "ga-starboard")
        # Step e: start
        podman.container_start.assert_called_once_with("gs-alpha")

    def test_migration_gateway_not_ready_returns_false(self) -> None:
        """Gateway not ready after migration → returns False."""
        podman = self._make_podman(container_networks=["ga-net"])
        with patch.object(lifecycle, "_wait_gateway", return_value=False):
            result = lifecycle._migrate_crew_network(podman, "alpha", "gs-alpha")
        self.assertFalse(result)

    def test_neither_network_is_noop(self) -> None:
        """Container on neither ga-net nor ga-starboard → skip (no-op), return True."""
        podman = self._make_podman(container_networks=["some-other-net"])
        result = lifecycle._migrate_crew_network(podman, "alpha", "gs-alpha")
        self.assertTrue(result)
        podman.container_stop.assert_not_called()
        podman.network_connect.assert_not_called()

    def test_migration_exception_returns_false(self) -> None:
        """Exception during migration steps → returns False."""
        podman = self._make_podman(container_networks=["ga-net"])
        podman.container_stop.side_effect = RuntimeError("stop failed")
        result = lifecycle._migrate_crew_network(podman, "alpha", "gs-alpha")
        self.assertFalse(result)


class ReconcileRegistryMigrationTests(unittest.TestCase):
    """Tests for migration integration in _reconcile_registry."""

    def _run_reconcile_with_crew(
        self,
        container_networks: list[str],
        migrate_result: bool = True,
        container_running: bool = False,
    ) -> dict:
        """Run _reconcile_registry with a single crew and capture registry updates."""
        reg = {"crews": {"alpha": {"container": "gs-alpha", "status": "running"}}}

        podman = MagicMock()
        podman.container_exists.return_value = True
        podman.container_is_running.return_value = container_running
        podman._req.return_value = []  # no containers for login sweep or ga-net check

        with (
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(lifecycle, "_registry_lock"),
            patch.object(lifecycle, "_load_registry", return_value=reg),
            patch.object(lifecycle, "_save_registry"),
            patch.object(lifecycle, "_migrate_crew_network", return_value=migrate_result),
            patch.object(lifecycle, "_nuke_login_container"),
        ):
            lifecycle._reconcile_registry()

        return reg

    def test_migration_failure_marks_crew_stopped(self) -> None:
        """When _migrate_crew_network returns False, crew is marked stopped."""
        reg = self._run_reconcile_with_crew(
            container_networks=["ga-net"], migrate_result=False
        )
        # The registry is loaded fresh in the write-back pass; we verify the
        # _save_registry was called with stopped status via checking updates
        # by inspecting _migrate_crew_network return value side effects.
        # Because _load_registry is mocked to return the same object, the
        # update is visible in the returned reg dict.
        self.assertEqual(reg["crews"]["alpha"]["status"], "stopped")

    def test_migration_success_does_not_mark_crew_stopped(self) -> None:
        """When _migrate_crew_network returns True and container is running, no stop update."""
        reg = self._run_reconcile_with_crew(
            container_networks=["ga-starboard"], migrate_result=True, container_running=True
        )
        self.assertNotEqual(reg["crews"]["alpha"].get("status"), "stopped")

    def test_ga_net_removal_attempted_when_empty(self) -> None:
        """ga-net removal is attempted when _req returns empty container list."""
        podman = MagicMock()
        podman.container_exists.return_value = True
        podman.container_is_running.return_value = True
        # _req returns empty list (no containers on ga-net)
        podman._req.return_value = []

        reg = {"crews": {"alpha": {"container": "gs-alpha", "status": "running"}}}
        with (
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(lifecycle, "_registry_lock"),
            patch.object(lifecycle, "_load_registry", return_value=reg),
            patch.object(lifecycle, "_save_registry"),
            patch.object(lifecycle, "_migrate_crew_network", return_value=True),
            patch.object(lifecycle, "_nuke_login_container"),
        ):
            lifecycle._reconcile_registry()

        podman.network_rm.assert_called_once_with("ga-net")

    def test_ga_net_removal_skipped_when_has_containers(self) -> None:
        """ga-net removal is skipped when containers are still on ga-net."""
        podman = MagicMock()
        podman.container_exists.return_value = True
        podman.container_is_running.return_value = True
        # _req returns a container with "ga-net" in its Networks dict
        podman._req.return_value = [{"Networks": {"ga-net": {}}, "Names": ["/old-crew"]}]

        reg = {"crews": {"alpha": {"container": "gs-alpha", "status": "running"}}}
        with (
            patch.object(lifecycle, "_get_podman", return_value=podman),
            patch.object(lifecycle, "_registry_lock"),
            patch.object(lifecycle, "_load_registry", return_value=reg),
            patch.object(lifecycle, "_save_registry"),
            patch.object(lifecycle, "_migrate_crew_network", return_value=True),
            patch.object(lifecycle, "_nuke_login_container"),
        ):
            lifecycle._reconcile_registry()

        podman.network_rm.assert_not_called()


# ── 7.11: PodmanClient network helpers ───────────────────────────────────────

class PodmanNetworkHelperTests(unittest.TestCase):
    """Tests for PodmanClient.network_connect, network_disconnect, container_networks."""

    def _make_client(self) -> tuple:
        """Return (client, fake_inner_client) pair for testing."""
        import transport.podman as podman_mod
        client = podman_mod.PodmanClient.__new__(podman_mod.PodmanClient)
        client._c = MagicMock()
        return client

    def test_network_connect_calls_correct_endpoint(self) -> None:
        """network_connect POSTs to /libpod/networks/{network}/connect."""
        client = self._make_client()
        resp = MagicMock()
        resp.status_code = 200
        client._c.post.return_value = resp
        client.network_connect("gs-alpha", "ga-starboard")
        client._c.post.assert_called_once_with(
            "/libpod/networks/ga-starboard/connect",
            json={"Container": "gs-alpha"},
        )

    def test_network_connect_409_is_idempotent(self) -> None:
        """network_connect treats 409 (already connected) as success, no raise."""
        client = self._make_client()
        resp = MagicMock()
        resp.status_code = 409
        client._c.post.return_value = resp
        # Should not raise
        client.network_connect("gs-alpha", "ga-starboard")

    def test_network_disconnect_calls_correct_endpoint(self) -> None:
        """network_disconnect POSTs to /libpod/networks/{network}/disconnect."""
        client = self._make_client()
        resp = MagicMock()
        resp.status_code = 200
        client._c.post.return_value = resp
        client.network_disconnect("gs-alpha", "ga-net")
        client._c.post.assert_called_once_with(
            "/libpod/networks/ga-net/disconnect",
            json={"Container": "gs-alpha", "Force": True},
        )

    def test_container_networks_parses_network_settings(self) -> None:
        """container_networks extracts network names from NetworkSettings.Networks."""
        client = self._make_client()
        client._c.get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={
                "NetworkSettings": {
                    "Networks": {
                        "ga-starboard": {"IPAddress": "10.89.0.5"},
                        "ga-portside": {"IPAddress": "10.88.0.2"},
                    }
                }
            }),
        )
        networks = client.container_networks("gs-alpha")
        self.assertIn("ga-starboard", networks)
        self.assertIn("ga-portside", networks)
        self.assertEqual(len(networks), 2)

    def test_container_networks_returns_empty_on_missing_container(self) -> None:
        """container_networks returns [] when container_inspect raises."""
        client = self._make_client()
        client._c.get.return_value = MagicMock(
            status_code=404,
            raise_for_status=MagicMock(side_effect=Exception("not found")),
        )
        networks = client.container_networks("gs-missing")
        self.assertEqual(networks, [])
