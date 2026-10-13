"""Unit tests for ``_handle_crew_ui_ws_proxy`` (trn-236 task 1.1).

Covers:
- Missing-dependency path (``_websockets`` or ``_StarletteWebSocket`` is None)
  → sends websocket.close with code 1011.
- Upstream connection failure before client accept
  → sends websocket.close with code 1011 (D1: real close-code, not HTTP 502).
- Resolved crew path yields 404 or 502
  → sends websocket.close with code 1008 (404) or 1011 (502).
- Normal bidirectional relay
  → client frames forwarded to upstream; upstream frames forwarded to client.
- Cookie near-expiry detected before upstream dial
  → _refresh_cookie called; connection proceeds normally.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

# ── Install stubs FIRST — before ANY transport import ────────────────────────
from tests.unit._stubs import install_import_stubs
install_import_stubs()

import transport.server as server  # noqa: E402


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_scope(path: str = "/crews/test-crew/ui/") -> dict:
    return {
        "type": "websocket",
        "path": path,
        "query_string": b"",
        "subprotocols": [],
    }


def _resolved_crew(crew_id: str = "test-crew", sub_path: str = "") -> tuple:
    return (crew_id, sub_path, {"cookie": "mc_token_5476=test; Max-Age=3600"})


def _make_upstream_mock(messages: list | None = None) -> AsyncMock:
    """Build a fake upstream websockets connection.

    ``messages`` is the list of text/bytes values to yield from the async-for
    iteration (simulating server→client frames).  Defaults to a single text
    frame.
    """
    if messages is None:
        messages = ["hello-from-upstream"]

    upstream = AsyncMock()
    upstream.subprotocol = None
    upstream.send = AsyncMock()
    upstream.close = AsyncMock()

    # Make the upstream an async iterator over ``messages``.
    async def _aiter(self_ignored):
        for m in messages:
            yield m

    upstream.__aiter__ = _aiter

    return upstream


def _make_websockets_connect_ctx(upstream: AsyncMock):
    """Return an async context manager that yields ``upstream``."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=upstream)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ── Test: missing-dependency path ────────────────────────────────────────────


class TestWsProxyMissingDependency(unittest.IsolatedAsyncioTestCase):
    """_StarletteWebSocket or _websockets is None → close frame 1011."""

    async def _run_handler(self, scope=None):
        scope = scope or _make_scope()
        sent = []

        async def receive():
            return {"type": "websocket.disconnect"}

        async def send(msg):
            sent.append(msg)

        await server._handle_crew_ui_ws_proxy(scope, receive, send)
        return sent

    async def test_no_websockets_sends_close_1011(self):
        with patch.object(server, "_websockets", None):
            sent = await self._run_handler()
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["type"], "websocket.close")
        self.assertEqual(sent[0]["code"], 1011)

    async def test_no_starlette_websocket_sends_close_1011(self):
        with patch.object(server, "_StarletteWebSocket", None):
            sent = await self._run_handler()
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["type"], "websocket.close")
        self.assertEqual(sent[0]["code"], 1011)


# ── Test: resolve-failure paths ───────────────────────────────────────────────


class TestWsProxyResolveFailure(unittest.IsolatedAsyncioTestCase):
    """404 → close 1008; 502 → close 1011.

    The handler calls ``await ws.close(code=...)`` on the Starlette WebSocket
    (not on the raw ASGI ``send``).  We capture the close code via a fake
    WebSocket class that records arguments to ``close()``.
    """

    async def _run_with_resolve_response(self, status_code: int) -> list:
        # Create an instance using server.Response directly — the same class
        # that `isinstance(resolved, Response)` tests inside the handler.  This
        # is robust to test-ordering differences where the starlette stub may or
        # may not be installed when this test runs.
        fake_resp = server.Response(content=b"", status_code=status_code)

        close_codes: list = []

        class FakeWS:
            scope = _make_scope()

            async def close(self, code: int = 1000) -> None:
                close_codes.append(code)

            async def accept(self, **_kw) -> None:
                pass

            async def receive(self) -> dict:
                return {"type": "websocket.disconnect"}

            async def send_text(self, t: str) -> None:
                pass

            async def send_bytes(self, b: bytes) -> None:
                pass

        fake_ws_cls = Mock(return_value=FakeWS())
        scope = _make_scope()

        async def _fake_resolve(path, **_kw):
            return fake_resp

        with (
            patch.object(server, "_resolve_crew_for_proxy", side_effect=_fake_resolve),
            patch.object(server, "_StarletteWebSocket", fake_ws_cls),
        ):
            await server._handle_crew_ui_ws_proxy(scope, AsyncMock(), AsyncMock())

        return close_codes

    async def test_resolve_404_sends_close_1008(self):
        codes = await self._run_with_resolve_response(404)
        self.assertTrue(codes, "Expected ws.close() to be called")
        self.assertEqual(codes[0], 1008)

    async def test_resolve_502_sends_close_1011(self):
        codes = await self._run_with_resolve_response(502)
        self.assertTrue(codes, "Expected ws.close() to be called")
        self.assertEqual(codes[0], 1011)


# ── Test: upstream connection failure before accept ──────────────────────────


class TestWsProxyUpstreamFailure(unittest.IsolatedAsyncioTestCase):
    """Upstream dial raises → sends websocket.close 1011 (D1)."""

    async def test_upstream_failure_closes_with_1011(self):
        scope = _make_scope()
        sent = []

        async def receive():
            return {"type": "websocket.disconnect"}

        async def send(msg):
            sent.append(msg)

        fake_connect = MagicMock()
        fake_connect.__aenter__ = AsyncMock(
            side_effect=OSError("connection refused")
        )
        fake_connect.__aexit__ = AsyncMock(return_value=False)

        fake_ws = Mock()
        fake_ws.scope = scope

        with (
            patch.object(server, "_resolve_crew_for_proxy",
                         return_value=_resolved_crew()),
            patch.object(server, "_cookie_near_expiry", return_value=False),
            patch.object(server, "_websockets") as mock_ws_mod,
        ):
            mock_ws_mod.connect = Mock(return_value=fake_connect)

            await server._handle_crew_ui_ws_proxy(scope, receive, send)

        close_frames = [m for m in sent if m.get("type") == "websocket.close"]
        self.assertTrue(close_frames,
                        f"Expected a websocket.close; got: {sent}")
        self.assertEqual(close_frames[0]["code"], 1011)


# ── Test: bidirectional relay ────────────────────────────────────────────────


class TestWsProxyBidirectionalRelay(unittest.IsolatedAsyncioTestCase):
    """Client→upstream and upstream→client frames are forwarded (D2)."""

    async def test_client_text_forwarded_to_upstream(self):
        scope = _make_scope()

        # Upstream yields nothing (relay from upstream side terminates quickly).
        upstream = _make_upstream_mock(messages=[])
        upstream_ctx = _make_websockets_connect_ctx(upstream)

        # Fake client WebSocket: emits one text frame then disconnects.
        client_messages = [
            {"type": "websocket.receive", "text": "hello-from-client"},
            {"type": "websocket.disconnect"},
        ]
        msg_iter = iter(client_messages)

        async def fake_receive():
            return next(msg_iter)

        accept_called = []
        send_text_calls = []
        send_bytes_calls = []
        close_calls = []

        # We need a real fake WS to capture send_text / send_bytes calls.
        # Use a class that records calls and drives the relay.
        class FakeClientWS:
            scope = _make_scope()
            accept = AsyncMock(side_effect=lambda **_kw: accept_called.append(True))
            receive = AsyncMock(side_effect=fake_receive)
            send_text = AsyncMock(side_effect=lambda t: send_text_calls.append(t))
            send_bytes = AsyncMock(side_effect=lambda b: send_bytes_calls.append(b))
            close = AsyncMock(side_effect=lambda **_kw: close_calls.append(True))

        fake_ws_cls = Mock(return_value=FakeClientWS())

        with (
            patch.object(server, "_resolve_crew_for_proxy",
                         return_value=_resolved_crew()),
            patch.object(server, "_cookie_near_expiry", return_value=False),
            patch.object(server, "_websockets") as mock_ws_mod,
            patch.object(server, "_StarletteWebSocket", fake_ws_cls),
        ):
            mock_ws_mod.connect = Mock(return_value=upstream_ctx)
            await server._handle_crew_ui_ws_proxy(scope, fake_receive, Mock())

        # The client text frame should have reached upstream.send.
        upstream.send.assert_called_with("hello-from-client")

    async def test_upstream_text_forwarded_to_client(self):
        scope = _make_scope()

        upstream = _make_upstream_mock(messages=["upstream-text"])
        upstream_ctx = _make_websockets_connect_ctx(upstream)

        # Client disconnects immediately (so _client_to_upstream terminates
        # first and the relay can resolve).
        async def fake_receive():
            return {"type": "websocket.disconnect"}

        send_text_calls = []

        class FakeClientWS:
            scope = _make_scope()
            accept = AsyncMock()
            receive = AsyncMock(side_effect=fake_receive)
            send_text = AsyncMock(side_effect=lambda t: send_text_calls.append(t))
            send_bytes = AsyncMock()
            close = AsyncMock()

        fake_ws_cls = Mock(return_value=FakeClientWS())

        with (
            patch.object(server, "_resolve_crew_for_proxy",
                         return_value=_resolved_crew()),
            patch.object(server, "_cookie_near_expiry", return_value=False),
            patch.object(server, "_websockets") as mock_ws_mod,
            patch.object(server, "_StarletteWebSocket", fake_ws_cls),
        ):
            mock_ws_mod.connect = Mock(return_value=upstream_ctx)
            await server._handle_crew_ui_ws_proxy(scope, fake_receive, Mock())

        self.assertIn("upstream-text", send_text_calls)

    async def test_upstream_bytes_forwarded_to_client(self):
        scope = _make_scope()

        upstream = _make_upstream_mock(messages=[b"\x00\x01\x02"])
        upstream_ctx = _make_websockets_connect_ctx(upstream)

        async def fake_receive():
            return {"type": "websocket.disconnect"}

        send_bytes_calls = []

        class FakeClientWS:
            scope = _make_scope()
            accept = AsyncMock()
            receive = AsyncMock(side_effect=fake_receive)
            send_text = AsyncMock()
            send_bytes = AsyncMock(side_effect=lambda b: send_bytes_calls.append(b))
            close = AsyncMock()

        fake_ws_cls = Mock(return_value=FakeClientWS())

        with (
            patch.object(server, "_resolve_crew_for_proxy",
                         return_value=_resolved_crew()),
            patch.object(server, "_cookie_near_expiry", return_value=False),
            patch.object(server, "_websockets") as mock_ws_mod,
            patch.object(server, "_StarletteWebSocket", fake_ws_cls),
        ):
            mock_ws_mod.connect = Mock(return_value=upstream_ctx)
            await server._handle_crew_ui_ws_proxy(scope, fake_receive, Mock())

        self.assertIn(b"\x00\x01\x02", send_bytes_calls)


# ── Test: cookie near-expiry refresh ────────────────────────────────────────


class TestWsProxyCookieRefresh(unittest.IsolatedAsyncioTestCase):
    """Cookie near-expiry → _refresh_cookie called before upstream dial (D3)."""

    async def test_refresh_called_when_cookie_near_expiry(self):
        scope = _make_scope()
        upstream = _make_upstream_mock(messages=[])
        upstream_ctx = _make_websockets_connect_ctx(upstream)

        async def fake_receive():
            return {"type": "websocket.disconnect"}

        class FakeClientWS:
            scope = _make_scope()
            accept = AsyncMock()
            receive = AsyncMock(side_effect=fake_receive)
            send_text = AsyncMock()
            send_bytes = AsyncMock()
            close = AsyncMock()

        fake_ws_cls = Mock(return_value=FakeClientWS())
        refresh_mock = Mock()

        with (
            patch.object(server, "_resolve_crew_for_proxy",
                         return_value=_resolved_crew()),
            patch.object(server, "_cookie_near_expiry", return_value=True),
            patch.object(server, "_refresh_cookie", refresh_mock),
            patch.object(server, "_websockets") as mock_ws_mod,
            patch.object(server, "_StarletteWebSocket", fake_ws_cls),
        ):
            mock_ws_mod.connect = Mock(return_value=upstream_ctx)
            await server._handle_crew_ui_ws_proxy(scope, fake_receive, Mock())

        refresh_mock.assert_called_once()

    async def test_no_refresh_when_cookie_fresh(self):
        scope = _make_scope()
        upstream = _make_upstream_mock(messages=[])
        upstream_ctx = _make_websockets_connect_ctx(upstream)

        async def fake_receive():
            return {"type": "websocket.disconnect"}

        class FakeClientWS:
            scope = _make_scope()
            accept = AsyncMock()
            receive = AsyncMock(side_effect=fake_receive)
            send_text = AsyncMock()
            send_bytes = AsyncMock()
            close = AsyncMock()

        fake_ws_cls = Mock(return_value=FakeClientWS())
        refresh_mock = Mock()

        with (
            patch.object(server, "_resolve_crew_for_proxy",
                         return_value=_resolved_crew()),
            patch.object(server, "_cookie_near_expiry", return_value=False),
            patch.object(server, "_refresh_cookie", refresh_mock),
            patch.object(server, "_websockets") as mock_ws_mod,
            patch.object(server, "_StarletteWebSocket", fake_ws_cls),
        ):
            mock_ws_mod.connect = Mock(return_value=upstream_ctx)
            await server._handle_crew_ui_ws_proxy(scope, fake_receive, Mock())

        refresh_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
