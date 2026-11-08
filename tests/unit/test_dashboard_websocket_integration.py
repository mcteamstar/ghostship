"""ASGI integration coverage for the generated Caddy dashboard proxy route.

The tests inspect Caddy's registered route configuration and exercise the
transport middleware and WebSocket proxy together with a disposable upstream
gateway double. No installed instance or external network is used.
"""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


class _Downstream:
    def __init__(self):
        self.called = False

    async def __call__(self, scope, receive, send):
        self.called = True
        await send({"type": "websocket.close", "code": 1008})


class TestDashboardWebSocketIntegration(unittest.TestCase):
    def _modules(self):
        from transport import auth, caddy, dashboard, server
        return auth, caddy, dashboard, server

    def _gate(self, api_key="dashboard-key"):
        _, _, dashboard, _ = self._modules()
        return dashboard.DashboardGate(
            session_ttl_secs=3600,
            api_key=api_key,
            external_url="https://dashboard.example:64057",
            port_base=64058,
            port_range_size=64,
            portal_domain="portal.example",
        )

    def _scope(self, gate, *, session=True, origin="https://dashboard.example:64058", token="portal-secret"):
        headers = []
        if token is not None:
            headers.append((b"x-transport-token", token.encode("ascii")))
        if session:
            session_token = gate._sessions.issue()
            headers.append((b"cookie", f"gs_session={session_token}".encode("ascii")))
        if origin is not None:
            headers.append((b"origin", origin.encode("latin-1")))
        if origin is not None:
            headers.extend([
                (b"x-portal-dashboard-host", b"dashboard.example:64058"),
                (b"x-portal-dashboard-proto", b"https"),
            ])
        return {
            "type": "websocket",
            "method": "GET",
            "path": "/crews/alpha/ui/ws",
            "query_string": b"",
            "headers": headers,
            "extensions": {"websocket.http.response": {}},
            "subprotocols": [],
        }

    def _invoke_websocket(self, gate, scope):
        auth, _, _, server = self._modules()
        messages = []
        upstream_calls = []
        resolved = AsyncMock(return_value=("alpha", "ws", SimpleNamespace(cookie="crew-cookie")))
        ready = asyncio.Event()
        browser_messages = []

        class FakeWebSocket:
            def __init__(self, ws_scope, receive, send):
                self.scope = ws_scope
                self._receive = receive
                self._send = send

            async def accept(self, *args, **kwargs):
                await self._send({"type": "websocket.accept"})

            async def receive(self):
                return await self._receive()

            async def send_text(self, value):
                await self._send({"type": "websocket.send", "text": value})

            async def send_bytes(self, value):
                await self._send({"type": "websocket.send", "bytes": value})

            async def close(self, *args, **kwargs):
                await self._send({"type": "websocket.close", "code": 1000})

        class FakeUpstream:
            subprotocol = None

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def send(self, value):
                browser_messages.append(value)
                ready.set()

            async def close(self):
                ready.set()

            def __aiter__(self):
                return self._frames()

            async def _frames(self):
                await ready.wait()
                yield "gateway-frame"

        def connect(url, **kwargs):
            upstream_calls.append((url, kwargs))
            return FakeUpstream()

        downstream = _Downstream()
        bearer = auth.BearerAuthMiddleware(
            downstream,
            api_key="dashboard-key",
            public_routes={("WS", "/crews/*/ui"): server._handle_crew_ui_ws_proxy},
        )
        app = auth.TransportSecretMiddleware(bearer, transport_secret="portal-secret")
        first_message = {"pending": True}

        async def receive():
            if first_message["pending"]:
                first_message["pending"] = False
                return {"type": "websocket.receive", "text": "browser-frame"}
            await ready.wait()
            return {"type": "websocket.disconnect", "code": 1000}

        async def send(message):
            messages.append(message)

        with (
            patch.object(server, "_dashboard_gate", gate),
            patch.object(server, "_StarletteWebSocket", FakeWebSocket),
            patch.object(server, "_websockets", SimpleNamespace(connect=connect)),
            patch.object(server, "_ws_exceptions", SimpleNamespace(ConnectionClosedError=type("Closed", (), {}))),
            patch.object(server, "_resolve_crew_for_proxy", resolved),
            patch.object(server, "_to_crew", side_effect=lambda crew_id, crew: crew),
            patch.object(server, "_cookie_near_expiry", return_value=False),
            patch.object(server, "_crew_cookie", return_value="mc_token_5476=crew-cookie"),
        ):
            _run(app(scope, receive, send))

        return messages, upstream_calls, browser_messages, resolved, downstream

    def test_caddy_registers_http_forward_auth_and_secret_protected_ws_route(self):
        _, caddy, _, _ = self._modules()
        portal = caddy.CaddyPortal(
            port=64057,
            api_key="dashboard-key",
            port_range_start=64058,
            port_range_size=64,
        )
        with patch("transport.caddy.httpx.put", return_value=MagicMock(status_code=200, text=""), create=True) as put:
            portal.register_crew("alpha", 64058)

        config = put.call_args.kwargs["json"]
        ws_proxy = config["routes"][0]["handle"][0]
        http_handles = config["routes"][1]["handle"]
        self.assertIn("/dashboard/auth", http_handles[0]["rewrite"]["uri"])
        headers = ws_proxy["headers"]["request"]["set"]
        self.assertEqual(headers["X-Transport-Token"], ["{file./run/secrets/ga-transport-secret}"])
        self.assertEqual(headers["X-Portal-Dashboard-Host"], ["{http.request.hostport}"])
        self.assertEqual(headers["X-Portal-Dashboard-Proto"], ["{http.request.scheme}"])

    def test_keyed_http_and_cookie_free_websocket_are_denied(self):
        _, _, _, server = self._modules()
        gate = self._gate()
        request_scope = {"type": "http", "method": "GET", "path": "/dashboard/auth", "headers": []}

        async def check_http():
            response = await gate.handle_auth(SimpleNamespace(scope=request_scope))
            messages = []
            async def send(message):
                messages.append(message)
            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}
            await response(request_scope, receive, send)
            return messages

        http_messages = _run(check_http())
        self.assertEqual(http_messages[0]["status"], 401)

        scope = self._scope(gate, session=False)
        messages, upstream, _, resolved, downstream = self._invoke_websocket(gate, scope)
        self.assertEqual(messages[0]["type"], "websocket.http.response.start")
        self.assertEqual(messages[0]["status"], 401)
        self.assertEqual(upstream, [])
        resolved.assert_not_awaited()
        self.assertFalse(downstream.called)

    def test_keyed_same_origin_websocket_relays_both_directions(self):
        gate = self._gate()
        messages, upstream, browser_messages, resolved, downstream = self._invoke_websocket(
            gate, self._scope(gate)
        )
        self.assertTrue(any(message["type"] == "websocket.accept" for message in messages))
        self.assertIn({"type": "websocket.send", "text": "gateway-frame"}, messages)
        self.assertEqual(browser_messages, ["browser-frame"])
        self.assertEqual(len(upstream), 1)
        self.assertEqual(upstream[0][0], "ws://gs-alpha:5476/ws")
        resolved.assert_awaited_once()
        self.assertFalse(downstream.called)

    def test_no_key_websocket_relays_without_session_or_origin(self):
        gate = self._gate(api_key="")
        scope = self._scope(gate, session=False, origin=None)
        messages, upstream, browser_messages, resolved, downstream = self._invoke_websocket(gate, scope)
        self.assertTrue(any(message["type"] == "websocket.accept" for message in messages))
        self.assertIn({"type": "websocket.send", "text": "gateway-frame"}, messages)
        self.assertEqual(browser_messages, ["browser-frame"])
        self.assertEqual(len(upstream), 1)
        resolved.assert_awaited_once()
        self.assertFalse(downstream.called)

    def test_bad_portal_secret_never_resolves_crew_or_opens_upstream(self):
        gate = self._gate()
        scope = self._scope(gate, token="forged-portal-secret")
        messages, upstream, _, resolved, downstream = self._invoke_websocket(gate, scope)
        self.assertEqual(messages[0]["type"], "websocket.http.response.start")
        self.assertEqual(messages[0]["status"], 401)
        self.assertEqual(upstream, [])
        resolved.assert_not_awaited()
        self.assertFalse(downstream.called)

    def test_invalid_session_never_resolves_crew_or_opens_upstream(self):
        gate = self._gate()
        scope = self._scope(gate)
        scope["headers"] = [
            (name, value) for name, value in scope["headers"] if name != b"cookie"
        ]
        scope["headers"].append((b"cookie", b"gs_session=forged-session"))
        messages, upstream, _, resolved, downstream = self._invoke_websocket(gate, scope)
        self.assertEqual(messages[0]["type"], "websocket.http.response.start")
        self.assertEqual(messages[0]["status"], 401)
        self.assertEqual(upstream, [])
        resolved.assert_not_awaited()
        self.assertFalse(downstream.called)


if __name__ == "__main__":
    unittest.main()
