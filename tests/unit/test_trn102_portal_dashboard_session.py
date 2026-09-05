"""Unit tests for TRN-102 — Portal dashboard session (transport-proxy routing).

Coverage:
  3.1 GET /crews/{id}/ui/ injects mc_token_5476 on the forwarded request
  3.2 UI proxy returns 404 for unknown crew
  3.3 _caddy_register_crew upstreams ga-transport (not gs-{id}:5476) with a
      /crews/{id}/ui rewrite and no Cookie header
  + helper unit tests for _parse_ttl_seconds / _jwt_exp / _cookie_near_expiry
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
import unittest
from unittest.mock import Mock, patch

# helpers installs httpx/mcp/starlette stubs in dependency-free environments.
from tests.unit.helpers import server, lifecycle  # noqa: F401


def _make_jwt(exp: int) -> str:
    """Build a minimal unsigned JWT-shaped token with the given exp claim."""
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    payload = base64.urlsafe_b64encode(
        json.dumps({"exp": exp}).encode()
    ).decode().rstrip("=")
    return f"{header}.{payload}.sig"


class _FakeUpstreamResponse:
    """httpx.Response-like stub returned by _async_http.stream()."""

    def __init__(self, status_code=200, content=b"", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = dict(headers or {})

    async def aread(self):
        return self.content

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _FakeStreamRequest:
    def __init__(self, method="GET", path="/crews/demo/ui", headers=None,
                 body=b"", query_string=b""):
        self.method = method
        self.scope = {
            "type": "http", "method": method, "path": path,
            "query_string": query_string,
        }
        self.headers = headers or {}
        self._body = body

    async def body(self):
        return self._body


# ── TTL / JWT helpers ────────────────────────────────────────────────────────

class TtlAndJwtHelperTests(unittest.TestCase):
    def test_parse_ttl_units(self) -> None:
        self.assertEqual(server._parse_ttl_seconds("24h"), 86400)
        self.assertEqual(server._parse_ttl_seconds("30m"), 1800)
        self.assertEqual(server._parse_ttl_seconds("3600s"), 3600)
        self.assertEqual(server._parse_ttl_seconds("2d"), 172800)
        self.assertEqual(server._parse_ttl_seconds("900"), 900)  # bare int = secs

    def test_parse_ttl_bad_value_defaults_to_24h(self) -> None:
        self.assertEqual(server._parse_ttl_seconds(""), 86400)
        self.assertEqual(server._parse_ttl_seconds("nonsense"), 86400)

    def test_jwt_exp_extracted(self) -> None:
        exp = int(time.time()) + 1000
        self.assertEqual(server._jwt_exp(_make_jwt(exp)), exp)

    def test_jwt_exp_none_for_non_jwt(self) -> None:
        self.assertIsNone(server._jwt_exp("plain-cookie"))

    def test_cookie_near_expiry_fresh_token_is_false(self) -> None:
        # Fresh 24h token → ~full TTL remaining → not near expiry.
        # TTL is hardcoded to "24h" in _cookie_near_expiry.
        fresh = _make_jwt(int(time.time()) + 86000)
        self.assertFalse(server._cookie_near_expiry(fresh))

    def test_cookie_near_expiry_old_token_is_true(self) -> None:
        # Only 10 min left on a 24h TTL → < 20% remaining → near expiry.
        # TTL is hardcoded to "24h" in _cookie_near_expiry.
        old = _make_jwt(int(time.time()) + 600)
        self.assertTrue(server._cookie_near_expiry(old))

    def test_cookie_near_expiry_non_jwt_is_true(self) -> None:
        # A non-JWT cookie cannot be reasoned about → treat as near-expiry.
        self.assertTrue(server._cookie_near_expiry("plain-cookie"))


# ── 3.1 — UI proxy injects mc_token_5476 ─────────────────────────────────────

class UiProxyCookieInjectionTests(unittest.TestCase):
    """3.1: GET /crews/{id}/ui/ injects the crew's session cookie."""

    def _run_proxy(self, crew: dict, path: str = "/crews/demo/ui/"):
        captured = {}

        class StreamCapture:
            def __call__(self_inner, method, url, headers=None, content=None):
                captured["headers"] = headers
                captured["url"] = url
                return _FakeUpstreamResponse(200, b"ok", {"content-type": "text/html"})

        async def run():
            with (
                patch.object(server, "_require_crew", return_value=crew),
                patch.object(server, "_ensure_crew_running", return_value=crew),
                patch.object(server, "_cookie_near_expiry", return_value=False),
                patch.object(server, "_async_http") as fake_http,
            ):
                fake_http.stream = StreamCapture()
                resp = await server._handle_crew_ui_proxy(_FakeStreamRequest(path=path))
            return resp, captured

        return asyncio.run(run())

    def test_ui_proxy_injects_mc_token_cookie(self) -> None:
        crew = {"container": "gs-demo", "cookie": "tok-abc"}
        resp, captured = self._run_proxy(crew)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(captured["headers"]["Cookie"], "mc_token_5476=tok-abc")

    def test_ui_proxy_strips_inbound_cookie(self) -> None:
        """An inbound browser Cookie header is replaced, not merged."""
        crew = {"container": "gs-demo", "cookie": "tok-xyz"}
        captured = {}

        class StreamCapture:
            def __call__(self_inner, method, url, headers=None, content=None):
                captured["headers"] = headers
                return _FakeUpstreamResponse(200, b"ok")

        async def run():
            with (
                patch.object(server, "_require_crew", return_value=crew),
                patch.object(server, "_ensure_crew_running", return_value=crew),
                patch.object(server, "_cookie_near_expiry", return_value=False),
                patch.object(server, "_async_http") as fake_http,
            ):
                fake_http.stream = StreamCapture()
                req = _FakeStreamRequest(
                    path="/crews/demo/ui/",
                    headers={"Cookie": "some_other=1", "Host": "x"},
                )
                return await server._handle_crew_ui_proxy(req)

        asyncio.run(run())
        self.assertEqual(captured["headers"]["Cookie"], "mc_token_5476=tok-xyz")
        self.assertNotIn("Host", captured["headers"])

    def test_ui_proxy_refreshes_cookie_when_near_expiry(self) -> None:
        crew = {"container": "gs-demo", "cookie": "stale"}
        refreshed = {"called": False}

        def fake_refresh(c, cid):
            refreshed["called"] = True
            c["cookie"] = "fresh"
            return True

        class StreamCapture:
            def __call__(self_inner, method, url, headers=None, content=None):
                self_inner.headers = headers
                return _FakeUpstreamResponse(200, b"ok")

        cap = StreamCapture()

        async def run():
            with (
                patch.object(server, "_require_crew", return_value=crew),
                patch.object(server, "_ensure_crew_running", return_value=crew),
                patch.object(server, "_cookie_near_expiry", return_value=True),
                patch.object(server, "_refresh_cookie", side_effect=fake_refresh),
                patch.object(server, "_async_http") as fake_http,
            ):
                fake_http.stream = cap
                return await server._handle_crew_ui_proxy(
                    _FakeStreamRequest(path="/crews/demo/ui/")
                )

        asyncio.run(run())
        self.assertTrue(refreshed["called"])
        self.assertEqual(cap.headers["Cookie"], "mc_token_5476=fresh")


# ── 3.2 — 404 / 503 error paths ──────────────────────────────────────────────

class ErrorPathTests(unittest.TestCase):
    def test_ui_proxy_unknown_crew_returns_404(self) -> None:
        async def run():
            with patch.object(server, "_require_crew", side_effect=KeyError("no such crew")):
                return await server._handle_crew_ui_proxy(
                    _FakeStreamRequest(path="/crews/ghost/ui/")
                )

        resp = asyncio.run(run())
        self.assertEqual(resp.status_code, 404)


# ── 3.3 — Caddy config routes to the transport, no cookie ────────────────────

class CaddyRoutesToTransportTests(unittest.TestCase):
    def _resp(self, status=200):
        r = Mock()
        r.status_code = status
        r.text = ""
        return r

    def test_crew_proxy_upstreams_transport_with_rewrite_and_no_cookie(self) -> None:
        mock_put = Mock(return_value=self._resp(200))
        with patch.object(server.httpx, "put", mock_put):
            server._caddy_register_crew("demo", 64058, crew_cookie="ignored-token")

        payload = mock_put.call_args.kwargs["json"]
        crew_proxy = payload["routes"][0]["handle"][-1]
        self.assertEqual(crew_proxy["upstreams"][0]["dial"], "ga-transport:8000")
        self.assertEqual(crew_proxy["rewrite"]["uri"],
                         "/crews/demo/ui{http.request.uri.path}")
        # No Cookie is injected by Caddy anymore — the transport handles it.
        self.assertNotIn("headers", crew_proxy)

    def test_crew_proxy_never_dials_crew_gateway_directly(self) -> None:
        mock_put = Mock(return_value=self._resp(200))
        with patch.object(server.httpx, "put", mock_put):
            server._caddy_register_crew("demo", 64058)
        body = json.dumps(mock_put.call_args.kwargs["json"])
        self.assertNotIn("gs-demo:5476", body)


# ── WS relay event-type dispatch ─────────────────────────────────────────────

class WsRelayEventDispatchTests(unittest.TestCase):
    """Regression: _upstream_to_client must dispatch on wsproto event types,
    not on raw bytes/str. upstream.receive() returns wsproto.events.Event
    objects (TextMessage, BytesMessage), never raw bytes or str.

    Bug present before TRN-102 banshee fix: isinstance(data, (bytes, bytearray))
    always False -> every frame called str(data) -> event object stringified
    instead of .data extracted -> all WS traffic upstream-to-browser corrupted.
    """

    def _make_ws_events(self):
        """Return (TextMessage, BytesMessage) from the live wsproto module."""
        try:
            import wsproto.events as ev
            return ev.TextMessage(data="hello from upstream"), ev.BytesMessage(data=b"\x00\x01\x02")
        except ImportError:
            self.skipTest("wsproto not available")

    def test_upstream_text_event_sends_text_not_stringified_object(self) -> None:
        """A TextMessage event must relay .data as text, not str(event)."""
        text_evt, _ = self._make_ws_events()

        sent_text: list = []
        sent_bytes: list = []

        class FakeClientWS:
            async def send_text(self, data): sent_text.append(data)
            async def send_bytes(self, data): sent_bytes.append(data)
            async def close(self): pass

        events = [text_evt]
        call_count = [0]

        async def fake_receive():
            if call_count[0] < len(events):
                event = events[call_count[0]]
                call_count[0] += 1
                return event
            raise Exception("disconnect")

        async def run():
            ws = FakeClientWS()

            async def _upstream_to_client():
                while True:
                    try:
                        data = await fake_receive()
                    except Exception:
                        await ws.close()
                        return
                    if server._WsBytesMessage is not None and isinstance(data, server._WsBytesMessage):
                        await ws.send_bytes(data.data)
                    elif server._WsTextMessage is not None and isinstance(data, server._WsTextMessage):
                        await ws.send_text(data.data)

            await _upstream_to_client()

        asyncio.run(run())
        self.assertEqual(sent_text, ["hello from upstream"])
        self.assertEqual(sent_bytes, [])
        # Guard: must not have sent the stringified event object
        if sent_text:
            self.assertNotIn("TextMessage", sent_text[0])

    def test_upstream_bytes_event_sends_bytes_not_stringified_object(self) -> None:
        """A BytesMessage event must relay .data as bytes, not str(event)."""
        _, bytes_evt = self._make_ws_events()

        sent_text: list = []
        sent_bytes: list = []

        class FakeClientWS:
            async def send_text(self, data): sent_text.append(data)
            async def send_bytes(self, data): sent_bytes.append(data)
            async def close(self): pass

        events = [bytes_evt]
        call_count = [0]

        async def fake_receive():
            if call_count[0] < len(events):
                event = events[call_count[0]]
                call_count[0] += 1
                return event
            raise Exception("disconnect")

        async def run():
            ws = FakeClientWS()

            async def _upstream_to_client():
                while True:
                    try:
                        data = await fake_receive()
                    except Exception:
                        await ws.close()
                        return
                    if server._WsBytesMessage is not None and isinstance(data, server._WsBytesMessage):
                        await ws.send_bytes(data.data)
                    elif server._WsTextMessage is not None and isinstance(data, server._WsTextMessage):
                        await ws.send_text(data.data)

            await _upstream_to_client()

        asyncio.run(run())
        self.assertEqual(sent_text, [])
        self.assertEqual(sent_bytes, [b"\x00\x01\x02"])


if __name__ == "__main__":
    unittest.main()
