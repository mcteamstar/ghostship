"""Integration coverage for the generated Caddy dashboard proxy route.

The tests inspect Caddy's registered route configuration and exercise the
transport middleware and WebSocket proxy with a disposable gateway. When Caddy
is installed, an optional process-level case sends traffic through Caddy and a
local transport server; no deployed instance or external network is used.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import closing
from http.client import HTTPConnection
from pathlib import Path
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
            headers.append((b"x-portal-dashboard-host", b"dashboard.example:64058"))
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
        self.assertNotIn("X-Portal-Dashboard-Proto", headers)

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


    def test_actual_caddy_process_denies_keyed_clients_and_relays_frames(self):
        caddy_binary = shutil.which("caddy")
        if caddy_binary is None:
            self.skipTest("Caddy executable is required for the process-level proxy test")
        # The unit conftest installs network-library stubs. Use a clean Python
        # process so this integration case exercises real ASGI and WebSockets.
        code = (
            "from tests.unit.test_dashboard_websocket_integration import "
            "TestDashboardWebSocketIntegration, _run; "
            "import shutil; "
            "_run(TestDashboardWebSocketIntegration()._exercise_actual_caddy_proxy(shutil.which('caddy')))"
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    async def _exercise_actual_caddy_proxy(self, caddy_binary):
        import uvicorn
        import websockets
        from starlette.responses import PlainTextResponse

        auth, caddy, dashboard, server = self._modules()
        gateway_frames = []
        gateway_handshakes = []

        async def disposable_gateway(connection):
            request = getattr(connection, "request", None)
            headers = getattr(request, "headers", None)
            if headers is None:
                headers = connection.request_headers
            gateway_handshakes.append((headers.get("Cookie"), headers.get("Origin")))
            frame = await connection.recv()
            gateway_frames.append(frame)
            await connection.send("gateway-frame")
            await connection.send(f"gateway-echo:{frame}")

        async with websockets.serve(disposable_gateway, "127.0.0.1", 0) as gateway:
            gateway_port = gateway.sockets[0].getsockname()[1]
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                caddy_port = probe.getsockname()[1]

            gate = dashboard.DashboardGate(
                session_ttl_secs=3600,
                api_key="dashboard-key",
                external_url=f"http://127.0.0.1:{caddy_port}",
                port_base=caddy_port,
                port_range_size=1,
            )
            gate.register_port("alpha", caddy_port)

            async def unused_downstream(scope, receive, send):
                response = PlainTextResponse("unhandled", status_code=404)
                await response(scope, receive, send)

            transport_app = auth.BearerAuthMiddleware(
                unused_downstream,
                api_key="dashboard-key",
                public_routes={
                    ("GET", "/dashboard/auth"): gate.handle_auth,
                    ("GET", "/crews/*/ui"): server._handle_crew_ui_proxy,
                    ("WS", "/crews/*/ui"): server._handle_crew_ui_ws_proxy,
                },
            )
            transport_app = auth.TransportSecretMiddleware(
                transport_app, transport_secret="portal-secret"
            )

            transport_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            transport_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            transport_listener.bind(("127.0.0.1", 0))
            transport_listener.listen(128)
            transport_listener.setblocking(False)
            transport_port = transport_listener.getsockname()[1]

            transport_server = uvicorn.Server(
                uvicorn.Config(
                    transport_app,
                    log_level="critical",
                    access_log=False,
                    lifespan="off",
                )
            )
            transport_thread = threading.Thread(
                target=transport_server.run,
                kwargs={"sockets": [transport_listener]},
                daemon=True,
            )
            transport_thread.start()
            caddy_process = None
            dashboard_gate_patcher = None
            try:
                deadline = asyncio.get_running_loop().time() + 5
                while not transport_server.started:
                    if not transport_thread.is_alive():
                        self.fail("Transport server exited before it started")
                    if asyncio.get_running_loop().time() >= deadline:
                        self.fail("Transport server did not start")
                    await asyncio.sleep(0.02)

                portal = caddy.CaddyPortal(
                    port=transport_port,
                    api_key="dashboard-key",
                    port_range_start=caddy_port,
                    port_range_size=1,
                )
                with patch(
                    "transport.caddy.httpx.put",
                    return_value=SimpleNamespace(status_code=200, text=""),
                ) as register:
                    portal.register_crew("alpha", caddy_port)
                caddy_server = json.loads(
                    json.dumps(register.call_args.kwargs["json"])
                )
                caddy_server["listen"] = [f"127.0.0.1:{caddy_port}"]
                caddy_server["automatic_https"] = {"disable": True}

                def adapt_generated_routes(value):
                    if isinstance(value, dict):
                        if value.get("handler") == "reverse_proxy":
                            value["upstreams"] = [
                                {"dial": f"127.0.0.1:{transport_port}"}
                            ]
                            request_headers = (
                                value.get("headers", {})
                                .get("request", {})
                                .get("set", {})
                            )
                            if request_headers.get("X-Transport-Token") == [
                                "{file./run/secrets/ga-transport-secret}"
                            ]:
                                request_headers["X-Transport-Token"] = [
                                    "portal-secret"
                                ]
                        for child in value.values():
                            adapt_generated_routes(child)
                    elif isinstance(value, list):
                        for child in value:
                            adapt_generated_routes(child)

                adapt_generated_routes(caddy_server)
                caddy_config = {
                    "admin": {"disabled": True},
                    "apps": {
                        "http": {
                            "servers": {"crew-alpha": caddy_server},
                        }
                    },
                }

                with tempfile.TemporaryDirectory() as temp_dir:
                    config_path = Path(temp_dir) / "caddy.json"
                    log_path = Path(temp_dir) / "caddy.log"
                    config_path.write_text(json.dumps(caddy_config))
                    with log_path.open("w+") as caddy_log:
                        caddy_process = subprocess.Popen(
                            [
                                caddy_binary,
                                "run",
                                "--config",
                                str(config_path),
                            ],
                            stdout=caddy_log,
                            stderr=caddy_log,
                        )
                        try:
                            deadline = asyncio.get_running_loop().time() + 10
                            while True:
                                if caddy_process.poll() is not None:
                                    caddy_log.flush()
                                    caddy_log.seek(0)
                                    self.fail(
                                        "Caddy exited before listening:\n"
                                        + caddy_log.read()
                                    )
                                try:
                                    with socket.create_connection(
                                        ("127.0.0.1", caddy_port), timeout=0.1
                                    ):
                                        break
                                except OSError:
                                    if asyncio.get_running_loop().time() >= deadline:
                                        caddy_log.flush()
                                        caddy_log.seek(0)
                                        self.fail(
                                            "Caddy did not listen:\n" + caddy_log.read()
                                        )
                                    await asyncio.sleep(0.05)

                            dashboard_gate_patcher = patch.object(
                                server, "_dashboard_gate", gate
                            )
                            dashboard_gate_patcher.start()

                            with closing(HTTPConnection(
                                "127.0.0.1", caddy_port, timeout=3
                            )) as client:
                                client.request("GET", "/")
                                response = client.getresponse()
                                response.read()
                            self.assertEqual(response.status, 401)

                            ws_url = f"ws://127.0.0.1:{caddy_port}/ws"
                            ws_origin = f"http://127.0.0.1:{caddy_port}"
                            status_exceptions = tuple(
                                error_type
                                for error_type in (
                                    getattr(websockets.exceptions, "InvalidStatus", None),
                                    getattr(
                                        websockets.exceptions,
                                        "InvalidStatusCode",
                                        None,
                                    ),
                                )
                                if isinstance(error_type, type)
                            )
                            try:
                                async with websockets.connect(
                                    ws_url,
                                    origin=ws_origin,
                                    open_timeout=3,
                                ):
                                    self.fail("Cookie-free WebSocket unexpectedly opened")
                            except status_exceptions as exc:
                                status = getattr(
                                    getattr(exc, "response", None), "status_code", None
                                )
                                if status is None:
                                    status = getattr(exc, "status_code", None)
                                self.assertEqual(status, 401)

                            resolved = AsyncMock(
                                return_value=(
                                    "alpha",
                                    "ws",
                                    SimpleNamespace(cookie="disposable-cookie"),
                                )
                            )
                            real_connect = server._websockets.connect
                            upstream_dials = []

                            def connect_disposable_gateway(url, *args, **kwargs):
                                upstream_dials.append(url)
                                if url.startswith("ws://gs-alpha:5476/"):
                                    url = url.replace(
                                        "ws://gs-alpha:5476",
                                        f"ws://127.0.0.1:{gateway_port}",
                                        1,
                                    )
                                return real_connect(url, *args, **kwargs)

                            session_token = gate._sessions.issue()
                            with (
                                patch.object(
                                    server,
                                    "_resolve_crew_for_proxy",
                                    resolved,
                                ),
                                patch.object(
                                    server,
                                    "_to_crew",
                                    side_effect=lambda crew_id, crew: crew,
                                ),
                                patch.object(
                                    server, "_cookie_near_expiry", return_value=False
                                ),
                                patch.object(
                                    server,
                                    "_crew_cookie",
                                    return_value="mc_token_5476=disposable-crew-cookie",
                                ),
                                patch.object(
                                    server._websockets,
                                    "connect",
                                    connect_disposable_gateway,
                                ),
                            ):
                                async with real_connect(
                                    ws_url,
                                    origin=ws_origin,
                                    additional_headers={
                                        "Cookie": f"gs_session={session_token}"
                                    },
                                    open_timeout=3,
                                ) as client:
                                    await client.send("browser-frame")
                                    frames = [
                                        await asyncio.wait_for(client.recv(), timeout=3)
                                        for _ in range(2)
                                    ]

                            self.assertEqual(
                                frames,
                                ["gateway-frame", "gateway-echo:browser-frame"],
                            )
                            self.assertEqual(gateway_frames, ["browser-frame"])
                            self.assertEqual(
                                upstream_dials, ["ws://gs-alpha:5476/ws"]
                            )
                            self.assertEqual(
                                gateway_handshakes,
                                [
                                    (
                                        "mc_token_5476=disposable-crew-cookie",
                                        "http://localhost:5476",
                                    )
                                ],
                            )
                            resolved.assert_awaited_once()
                        finally:
                            if dashboard_gate_patcher is not None:
                                dashboard_gate_patcher.stop()
                            if caddy_process is not None:
                                caddy_process.terminate()
                                try:
                                    caddy_process.wait(timeout=5)
                                except subprocess.TimeoutExpired:
                                    caddy_process.kill()
                                    caddy_process.wait(timeout=5)
            finally:
                transport_server.should_exit = True
                transport_thread.join(timeout=5)
                transport_listener.close()


if __name__ == "__main__":
    unittest.main()
