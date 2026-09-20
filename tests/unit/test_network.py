"""Unit tests for network split -- NetworkConstants, TransportSecretMiddleware, crew network migration, PodmanClient network helpers, and Caddy transport secret wiring."""

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


# ── : Constants ────────────────────────────────────────────────────────────

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


# ── : TransportSecretMiddleware ──────────────────────────────────────────

class TransportSecretMiddlewareTests(unittest.TestCase):
    """Tests for TransportSecretMiddleware (outermost gate)."""

    def test_missing_header_returns_401(self) -> None:
        """Request with no X-Transport-Token header → 401."""
        downstream = _FakeDownstream()
        mw = server.TransportSecretMiddleware(downstream, transport_secret="correct-secret")
        scope = _http_scope()  # no headers
        status, headers, body = _run_asgi(mw, scope)
        self.assertEqual(status, 401)
        self.assertFalse(downstream.called)

    def test_correct_header_passes_through(self) -> None:
        """Request with correct X-Transport-Token → forwarded to downstream (200)."""
        downstream = _FakeDownstream()
        secret = "my-portal-secret-abc123"
        mw = server.TransportSecretMiddleware(downstream, transport_secret=secret)
        scope = _http_scope(headers=[(b"x-transport-token", secret.encode())])
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 200)
        self.assertTrue(downstream.called)

    def test_wrong_header_value_returns_401(self) -> None:
        """Request with wrong X-Transport-Token value → 401."""
        downstream = _FakeDownstream()
        mw = server.TransportSecretMiddleware(downstream, transport_secret="correct")
        scope = _http_scope(headers=[(b"x-transport-token", b"wrong")])
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 401)
        self.assertFalse(downstream.called)

    def test_empty_transport_secret_is_pass_through(self) -> None:
        """When transport_secret is empty, middleware is a transparent pass-through."""
        downstream = _FakeDownstream()
        mw = server.TransportSecretMiddleware(downstream, transport_secret="")
        scope = _http_scope()  # no X-Transport-Token header
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 200)
        self.assertTrue(downstream.called)

    def test_non_http_scope_passes_through(self) -> None:
        """Non-HTTP scopes (websocket, lifespan) pass through unchanged."""
        downstream = _FakeDownstream()
        mw = server.TransportSecretMiddleware(downstream, transport_secret="secret")
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
        mw = server.TransportSecretMiddleware(downstream, transport_secret="secret")
        scope = _http_scope()
        status, _, body = _run_asgi(mw, scope)
        self.assertEqual(status, 401)
        self.assertEqual(body, b"Unauthorized")


# ── : PodmanClient network helpers ───────────────────────────────────────

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

    def test_network_connect_raises_on_non_409_error(self) -> None:
        """Fix 5: network_connect raises on a non-409 HTTP error."""
        import httpx2 as httpx
        client = self._make_client()
        resp = MagicMock()
        resp.status_code = 500
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=resp
        )
        client._c.post.return_value = resp
        with self.assertRaises(httpx.HTTPStatusError):
            client.network_connect("gs-alpha", "ga-starboard")

    def test_network_connect_200_does_not_raise(self) -> None:
        """Fix 5: network_connect succeeds silently on 200."""
        client = self._make_client()
        resp = MagicMock()
        resp.status_code = 200
        client._c.post.return_value = resp
        # Should not raise
        client.network_connect("gs-alpha", "ga-starboard")

    def test_network_connect_204_does_not_raise(self) -> None:
        """Fix 5: network_connect succeeds silently on 204."""
        client = self._make_client()
        resp = MagicMock()
        resp.status_code = 204
        client._c.post.return_value = resp
        # Should not raise
        client.network_connect("gs-alpha", "ga-starboard")


# ── Regression:  secret header must reach the per-crew dashboard route ──
#
# The TransportSecretMiddleware tests above (7.2-7.5) only prove the gate
# itself works in isolation. They do NOT prove that _caddy_register_crew
# (, in transport/server.py) actually sends the header Caddy
# needs to get past that gate. This class closes that gap directly: it was
# the missing link that let a real crew dashboard 401 in production while
# every existing unit test still passed.

class CaddyRegisterCrewTransportSecretTests(unittest.TestCase):
    """_caddy_register_crew must inject X-Transport-Token on every route it builds."""

    def _resp(self, status: int = 200) -> Mock:
        resp = Mock()
        resp.status_code = status
        resp.text = ""
        return resp

    def test_crew_proxy_dials_configured_port_not_a_stale_literal(self) -> None:
        """The crew reverse_proxy must dial ga-transport:{PORT} (server.PORT),
        not a hardcoded literal left over from before the  port
        consolidation (previously a stale ':8000' that no process listened on,
        causing every dashboard request to 502)."""
        mock_put = Mock(return_value=self._resp(200))
        with patch.object(server.httpx, "put", mock_put):
            server._caddy_register_crew("alpha", 64058)

        payload = mock_put.call_args.kwargs["json"]
        crew_proxy = payload["routes"][0]["handle"][-1]
        self.assertEqual(crew_proxy["upstreams"][0]["dial"], f"ga-transport:{server.PORT}")

    def test_crew_proxy_carries_transport_secret_header(self) -> None:
        """Without GA_API_KEY, the sole crew-proxy handler still carries the
        portal secret header — TransportSecretMiddleware rejects ga-transport
        requests missing it regardless of GA_API_KEY."""
        mock_put = Mock(return_value=self._resp(200))
        with patch.object(server.httpx, "put", mock_put):
            server._caddy_register_crew("alpha", 64058)

        payload = mock_put.call_args.kwargs["json"]
        crew_proxy = payload["routes"][0]["handle"][-1]
        self.assertEqual(
            crew_proxy["headers"]["request"]["set"]["X-Transport-Token"],
            ["{file./run/secrets/ga-transport-secret}"],
        )

    def test_forward_auth_handler_carries_transport_secret_header(self) -> None:
        """With GA_API_KEY set, the forward_auth handler (which also dials
        ga-transport) must carry the same portal secret header."""
        mock_put = Mock(return_value=self._resp(200))
        with (
            patch.object(server, "GA_API_KEY", "some-key"),
            patch.object(server.httpx, "put", mock_put),
        ):
            server._caddy_register_crew("alpha", 64058)

        payload = mock_put.call_args.kwargs["json"]
        fwd_auth = payload["routes"][0]["handle"][0]
        self.assertEqual(
            fwd_auth["headers"]["request"]["set"]["X-Transport-Token"],
            ["{file./run/secrets/ga-transport-secret}"],
        )
