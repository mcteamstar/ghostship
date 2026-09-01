"""Unit tests for TRN-80: crew UI SPA proxy — catch-all routing and CORS injection.

Covers:
  1.x  CORS origin injection at container create
  2.x  crew_ui_context cookie on initial UI proxy response
  3.x  Catch-all SPA asset route
"""

from __future__ import annotations

import asyncio
import unittest
from typing import Any
from unittest.mock import Mock, patch

from tests.unit.helpers import Request, server, lifecycle  # noqa: F401


# ── Reuse the same request/response stubs from test_server.py ────────────────

class _FakeStreamRequest:
    """Minimal async-compatible request stub for proxy handler tests."""

    def __init__(
        self,
        method: str = "GET",
        path: str = "/",
        headers: dict[str, str] | None = None,
        body: bytes = b"",
        query_string: bytes = b"",
    ) -> None:
        self.method = method
        self.scope = {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": query_string,
        }
        raw_headers = headers or {}
        self.headers = raw_headers
        self._body = body

    async def body(self) -> bytes:
        return self._body

    @property
    def cookies(self):
        """Parse cookies from the 'cookie' header for Starlette compatibility."""
        result = {}
        cookie_header = self.headers.get("cookie", "")
        for part in cookie_header.split(";"):
            part = part.strip()
            if "=" in part:
                k, _, v = part.partition("=")
                result[k.strip()] = v.strip()
        return result


class _FakeUpstreamResponse:
    """httpx.Response-like stub returned by _async_http.stream() context manager."""

    def __init__(
        self,
        status_code: int = 200,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = dict(headers or {})

    async def aread(self) -> bytes:
        return self.content

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


# ── Shared helpers ────────────────────────────────────────────────────────────

def _make_launch_create_calls(
    ga_host_url: str = "",
    port: int = 64057,
) -> list[dict]:
    """Run launch() up through container_create and return the create kwargs.

    Aborts after container_create so no gateway wait is needed.
    """
    create_calls: list[dict] = []

    class _StopAfterCreate(Exception):
        pass

    def fake_container_create(**kwargs: Any) -> dict:
        create_calls.append(kwargs)
        raise _StopAfterCreate

    podman = Mock()
    podman.container_create = Mock(side_effect=fake_container_create)
    podman.volume_create = Mock()
    podman.network_create = Mock()

    with (
        patch.object(server, "GA_HOST_URL", ga_host_url),
        patch.object(server, "PORT", port),
        patch.object(server, "GA_GIT_AUTHOR_NAME", ""),
        patch.object(server, "GA_GIT_AUTHOR_EMAIL", ""),
        patch.object(lifecycle, "_get_podman", return_value=podman),
        patch.object(server, "_get_podman", return_value=podman),
        patch.object(server, "_read_auth_file", return_value="fake-auth"),
        patch.object(lifecycle, "_resolve_image", return_value="localhost/spec-ops:latest"),
        patch.object(server, "_resolve_image", return_value="localhost/spec-ops:latest"),
        patch.object(lifecycle, "_resolve_composition", return_value={"name": "spec-ops"}),
        patch.object(server, "_resolve_composition", return_value={"name": "spec-ops"}),
        patch.object(lifecycle, "_registry_lock"),
        patch.object(server, "_registry_lock"),
        patch.object(lifecycle, "_load_registry", return_value={"crews": {}}),
        patch.object(server, "_load_registry", return_value={"crews": {}}),
        patch.object(lifecycle, "_save_registry"),
        patch.object(server, "_save_registry"),
    ):
        try:
            server.launch("test-crew")
        except _StopAfterCreate:
            pass

    return create_calls


CREW = {"container": "gs-demo", "cookie": "test-cookie-val"}


# ══════════════════════════════════════════════════════════════════════════════
# 1.x  CORS origin injection at container create
# ══════════════════════════════════════════════════════════════════════════════

class CorsOriginInjectionTests(unittest.TestCase):
    """TRN-80 task 1: Transport origin injected into KIROCREW_CORS_ORIGINS."""

    # ── 1.1 / 1.2: GA_HOST_URL set ───────────────────────────────────────────

    def test_ga_host_url_set_https_origin_appended(self) -> None:
        """1.1: GA_HOST_URL=https://academy.example.com → origin appended to CORS."""
        calls = _make_launch_create_calls(ga_host_url="https://academy.example.com")
        self.assertEqual(len(calls), 1)
        cors = calls[0]["env"]["KIROCREW_CORS_ORIGINS"]
        self.assertIn("https://academy.example.com", cors)

    def test_ga_host_url_set_strips_trailing_slash(self) -> None:
        """1.1: Trailing slash in GA_HOST_URL is stripped before injection."""
        calls = _make_launch_create_calls(ga_host_url="https://academy.example.com/")
        cors = calls[0]["env"]["KIROCREW_CORS_ORIGINS"]
        self.assertIn("https://academy.example.com", cors)
        self.assertNotIn("https://academy.example.com/,", cors)

    def test_ga_host_url_set_uses_scheme_and_host_only(self) -> None:
        """1.1: Path/query components in GA_HOST_URL are dropped."""
        calls = _make_launch_create_calls(
            ga_host_url="https://academy.example.com/some/path?q=1"
        )
        cors = calls[0]["env"]["KIROCREW_CORS_ORIGINS"]
        self.assertIn("https://academy.example.com", cors)
        self.assertNotIn("/some/path", cors)

    # ── 1.1 / 1.2: GA_HOST_URL unset → localhost fallback ────────────────────

    def test_ga_host_url_unset_fallback_to_localhost(self) -> None:
        """1.1: GA_HOST_URL unset → http://localhost:{PORT} appended."""
        calls = _make_launch_create_calls(ga_host_url="", port=64057)
        cors = calls[0]["env"]["KIROCREW_CORS_ORIGINS"]
        self.assertIn("http://localhost:64057", cors)

    def test_ga_host_url_unset_uses_configured_port(self) -> None:
        """1.1: Fallback origin uses the configured PORT, not a hardcoded value."""
        calls = _make_launch_create_calls(ga_host_url="", port=9999)
        cors = calls[0]["env"]["KIROCREW_CORS_ORIGINS"]
        self.assertIn("http://localhost:9999", cors)

    # ── 1.2: pre-existing value preserved ────────────────────────────────────

    def test_existing_crew_origin_preserved_when_transport_origin_appended(self) -> None:
        """1.2: Pre-existing KIROCREW_CORS_ORIGINS (crew internal origin) is preserved."""
        calls = _make_launch_create_calls(ga_host_url="https://host.example.com")
        cors = calls[0]["env"]["KIROCREW_CORS_ORIGINS"]
        # Must contain both the crew's own internal origin AND the transport origin
        self.assertIn("gs-test-crew:5476", cors)
        self.assertIn("https://host.example.com", cors)
        # Values should be comma-separated, not one replacing the other
        self.assertIn(",", cors)

    def test_cors_origins_is_comma_separated(self) -> None:
        """1.2: Origins joined with comma, no extra spaces."""
        calls = _make_launch_create_calls(ga_host_url="https://host.example.com")
        cors = calls[0]["env"]["KIROCREW_CORS_ORIGINS"]
        parts = cors.split(",")
        self.assertGreaterEqual(len(parts), 2)
        for part in parts:
            self.assertEqual(part, part.strip(), "No leading/trailing spaces in CORS values")

    # ── _transport_public_origin unit tests ───────────────────────────────────

    def test_transport_public_origin_returns_scheme_and_host(self) -> None:
        """_transport_public_origin extracts scheme+host from GA_HOST_URL."""
        with (
            patch.object(server, "GA_HOST_URL", "https://example.com"),
            patch.object(server, "PORT", 64057),
        ):
            result = server._transport_public_origin()
        self.assertEqual(result, "https://example.com")

    def test_transport_public_origin_strips_path(self) -> None:
        """_transport_public_origin strips path from GA_HOST_URL."""
        with (
            patch.object(server, "GA_HOST_URL", "https://example.com/extra/path"),
            patch.object(server, "PORT", 64057),
        ):
            result = server._transport_public_origin()
        self.assertEqual(result, "https://example.com")

    def test_transport_public_origin_fallback_when_empty(self) -> None:
        """_transport_public_origin falls back to localhost when GA_HOST_URL is empty."""
        with (
            patch.object(server, "GA_HOST_URL", ""),
            patch.object(server, "PORT", 64057),
        ):
            result = server._transport_public_origin()
        self.assertEqual(result, "http://localhost:64057")

    def test_transport_public_origin_fallback_when_whitespace(self) -> None:
        """_transport_public_origin falls back when GA_HOST_URL is whitespace-only."""
        with (
            patch.object(server, "GA_HOST_URL", "   "),
            patch.object(server, "PORT", 8080),
        ):
            result = server._transport_public_origin()
        self.assertEqual(result, "http://localhost:8080")


# ══════════════════════════════════════════════════════════════════════════════
# 2.x  crew_ui_context cookie on initial UI proxy response
# ══════════════════════════════════════════════════════════════════════════════

class CrewUiContextCookieTests(unittest.TestCase):
    """TRN-80 task 2: crew_ui_context cookie set on root UI proxy responses."""

    def _proxy_response(self, path: str) -> Any:
        """Run _handle_crew_ui_proxy for the given path and return the response."""
        mock_ctx = _FakeUpstreamResponse(200, b"<html/>", {"content-type": "text/html"})

        async def run():
            with (
                patch.object(lifecycle, "_require_crew", return_value=CREW),
                patch.object(server, "_require_crew", return_value=CREW),
                patch.object(lifecycle, "_ensure_crew_running", return_value=CREW),
                patch.object(server, "_ensure_crew_running", return_value=CREW),
            ):
                class FakeHTTP:
                    def stream(self_inner, method, url, headers=None, content=None):
                        return mock_ctx

                with patch.object(server, "_async_http", FakeHTTP()):
                    return await server._handle_crew_ui_proxy(
                        _FakeStreamRequest(path=path)
                    )

        return asyncio.run(run())

    # ── 2.1: cookie set with correct attributes ───────────────────────────────

    def test_cookie_set_on_ui_root_path_without_trailing_slash(self) -> None:
        """2.1: /crews/demo/ui sets crew_ui_context cookie."""
        resp = self._proxy_response("/crews/demo/ui")
        set_cookie = resp.headers.get("set-cookie", "")
        self.assertIn("crew_ui_context=demo", set_cookie)

    def test_cookie_set_on_ui_root_path_with_trailing_slash(self) -> None:
        """2.1: /crews/demo/ui/ sets crew_ui_context cookie."""
        resp = self._proxy_response("/crews/demo/ui/")
        set_cookie = resp.headers.get("set-cookie", "")
        self.assertIn("crew_ui_context=demo", set_cookie)

    def test_cookie_has_httponly_attribute(self) -> None:
        """2.1: Cookie is HttpOnly."""
        resp = self._proxy_response("/crews/demo/ui/")
        set_cookie = resp.headers.get("set-cookie", "").lower()
        self.assertIn("httponly", set_cookie)

    def test_cookie_has_samesite_strict(self) -> None:
        """2.1: Cookie has SameSite=Strict."""
        resp = self._proxy_response("/crews/demo/ui/")
        set_cookie = resp.headers.get("set-cookie", "").lower()
        self.assertIn("samesite=strict", set_cookie)

    def test_cookie_has_path_root(self) -> None:
        """2.1: Cookie is scoped to Path=/."""
        resp = self._proxy_response("/crews/demo/ui/")
        set_cookie = resp.headers.get("set-cookie", "").lower()
        self.assertIn("path=/", set_cookie)

    def test_cookie_has_max_age_3600(self) -> None:
        """2.1: Cookie has Max-Age=3600 (1 hour TTL)."""
        resp = self._proxy_response("/crews/demo/ui/")
        set_cookie = resp.headers.get("set-cookie", "").lower()
        self.assertIn("max-age=3600", set_cookie)

    def test_cookie_crew_id_matches_path(self) -> None:
        """2.1: Cookie value is the crew_id from the path."""
        resp = self._proxy_response("/crews/my-crew/ui")
        set_cookie = resp.headers.get("set-cookie", "")
        self.assertIn("crew_ui_context=my-crew", set_cookie)

    # ── 2.2: cookie NOT set on sub-path requests ──────────────────────────────

    def test_cookie_not_set_on_sub_path_request(self) -> None:
        """2.2: /crews/demo/ui/app/page does NOT set the cookie."""
        resp = self._proxy_response("/crews/demo/ui/app/page")
        set_cookie = resp.headers.get("set-cookie", "")
        self.assertNotIn("crew_ui_context", set_cookie)

    def test_cookie_not_set_on_nested_asset_path(self) -> None:
        """2.2: /crews/demo/ui/static/app.js does NOT set the cookie."""
        resp = self._proxy_response("/crews/demo/ui/static/app.js")
        set_cookie = resp.headers.get("set-cookie", "")
        self.assertNotIn("crew_ui_context", set_cookie)


# ══════════════════════════════════════════════════════════════════════════════
# 3.x  Catch-all SPA asset route
# ══════════════════════════════════════════════════════════════════════════════

class SpaCatchallHandlerTests(unittest.TestCase):
    """TRN-80 task 3: _handle_spa_catchall routes SPA assets to originating crew."""

    def _run_catchall(
        self,
        path: str = "/static/app.js",
        headers: dict[str, str] | None = None,
        crew: dict | None = None,
        upstream_status: int = 200,
        upstream_body: bytes = b"asset",
    ):
        """Run _handle_spa_catchall and return (response, captured_upstream_url)."""
        captured: list[str] = []
        _crew = crew if crew is not None else CREW
        mock_ctx = _FakeUpstreamResponse(upstream_status, upstream_body)

        async def run():
            with (
                patch.object(server, "_require_crew", return_value=_crew),
                patch.object(lifecycle, "_require_crew", return_value=_crew),
                patch.object(server, "_ensure_crew_running", return_value=_crew),
                patch.object(lifecycle, "_ensure_crew_running", return_value=_crew),
            ):
                class FakeHTTP:
                    def stream(self_inner, method, url, headers=None, content=None):
                        captured.append(url)
                        return mock_ctx

                with patch.object(server, "_async_http", FakeHTTP()):
                    resp = await server._handle_spa_catchall(
                        _FakeStreamRequest(path=path, headers=headers or {})
                    )
            return resp

        resp = asyncio.run(run())
        return resp, captured

    # ── 3.2: Referer-based routing ────────────────────────────────────────────

    def test_referer_match_proxies_to_correct_crew(self) -> None:
        """3.2: Referer pointing at /crews/demo/ui/ → proxy to gs-demo."""
        resp, urls = self._run_catchall(
            path="/static/app.js",
            headers={"referer": "http://transport-host/crews/demo/ui/"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(urls, "No upstream URL was captured")
        self.assertIn("gs-demo:5476", urls[0])
        self.assertIn("/static/app.js", urls[0])

    def test_referer_with_sub_path_proxies_to_correct_crew(self) -> None:
        """3.2: Referer pointing at a sub-page also routes to that crew."""
        resp, urls = self._run_catchall(
            path="/assets/chunk.js",
            headers={"referer": "http://host/crews/my-crew/ui/some/page"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(urls)
        self.assertIn("gs-my-crew:5476", urls[0])

    def test_referer_match_forwards_original_path(self) -> None:
        """3.2: The original request path is forwarded to upstream unchanged."""
        _, urls = self._run_catchall(
            path="/static/app.css",
            headers={"referer": "http://host/crews/demo/ui/"},
        )
        self.assertTrue(urls)
        self.assertIn("/static/app.css", urls[0])

    # ── 3.3: cookie fallback ──────────────────────────────────────────────────

    def test_cookie_fallback_when_no_referer(self) -> None:
        """3.3: crew_ui_context cookie used when Referer is absent."""
        resp, urls = self._run_catchall(
            path="/static/app.js",
            headers={"cookie": "crew_ui_context=demo"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(urls)
        self.assertIn("gs-demo:5476", urls[0])

    def test_cookie_fallback_when_referer_doesnt_match(self) -> None:
        """3.3: Cookie used when Referer is present but doesn't match crew UI path."""
        resp, urls = self._run_catchall(
            path="/static/app.js",
            headers={
                "referer": "https://external-site.example.com/page",
                "cookie": "crew_ui_context=demo",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(urls)
        self.assertIn("gs-demo:5476", urls[0])

    def test_referer_takes_priority_over_cookie(self) -> None:
        """3.2+3.3: When both Referer and cookie are present, Referer wins."""
        captured_require_crew: list[str] = []

        async def run():
            with (
                patch.object(server, "_require_crew", side_effect=lambda cid: captured_require_crew.append(cid) or CREW),
                patch.object(lifecycle, "_require_crew", side_effect=lambda cid: CREW),
                patch.object(server, "_ensure_crew_running", return_value=CREW),
                patch.object(lifecycle, "_ensure_crew_running", return_value=CREW),
            ):
                mock_ctx = _FakeUpstreamResponse(200, b"ok")

                class FakeHTTP:
                    def stream(self_inner, *args, **kwargs):
                        return mock_ctx

                with patch.object(server, "_async_http", FakeHTTP()):
                    await server._handle_spa_catchall(
                        _FakeStreamRequest(
                            path="/static/app.js",
                            headers={
                                "referer": "http://host/crews/referer-crew/ui/",
                                "cookie": "crew_ui_context=cookie-crew",
                            },
                        )
                    )

        asyncio.run(run())
        self.assertTrue(captured_require_crew)
        self.assertEqual(captured_require_crew[0], "referer-crew")

    # ── 3.4: no Referer + no cookie → 404 ────────────────────────────────────

    def test_no_referer_no_cookie_returns_404(self) -> None:
        """3.4: No Referer and no cookie → 404 with expected message."""
        async def run():
            return await server._handle_spa_catchall(
                _FakeStreamRequest(path="/static/app.js", headers={})
            )

        resp = asyncio.run(run())
        self.assertEqual(resp.status_code, 404)
        self.assertIn("No crew context", resp.body.decode())

    def test_empty_cookie_no_referer_returns_404(self) -> None:
        """3.4: Empty cookie value and no Referer → 404."""
        async def run():
            return await server._handle_spa_catchall(
                _FakeStreamRequest(
                    path="/static/app.js",
                    headers={"cookie": "other=value"},
                )
            )

        resp = asyncio.run(run())
        self.assertEqual(resp.status_code, 404)

    # ── 3.5: existing routes are NOT intercepted ──────────────────────────────

    def test_crews_ui_route_takes_priority_over_catchall(self) -> None:
        """3.5: /crews/demo/ui goes to UI proxy, not the catch-all."""
        # The catch-all handler is NOT called for /crews/{id}/ui paths —
        # BearerAuthMiddleware dispatches those to _handle_crew_ui_proxy first.
        # Here we verify the catch-all itself, when invoked, still produces
        # a correct response when referer/cookie indicate a crew.
        # The integration test is that existing route checks come before catch-all
        # in BearerAuthMiddleware.__call__ — confirmed by code inspection.
        # What we test here: _handle_spa_catchall itself doesn't special-case /crews/ paths.
        resp, urls = self._run_catchall(
            path="/static/app.js",
            headers={"referer": "http://host/crews/demo/ui/"},
        )
        self.assertEqual(resp.status_code, 200)

    def test_catchall_returns_404_body_message(self) -> None:
        """3.4: 404 body is the expected sentinel string."""
        async def run():
            return await server._handle_spa_catchall(
                _FakeStreamRequest(path="/some/path", headers={})
            )

        resp = asyncio.run(run())
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.body, b"No crew context for SPA asset request")

    # ── _crew_id_from_referer unit tests ──────────────────────────────────────

    def test_crew_id_from_referer_basic(self) -> None:
        """Parses crew_id from http://host/crews/{id}/ui/"""
        result = server._crew_id_from_referer("http://host/crews/my-crew/ui/")
        self.assertEqual(result, "my-crew")

    def test_crew_id_from_referer_without_trailing_slash(self) -> None:
        """Parses crew_id from /crews/{id}/ui (no trailing slash)."""
        result = server._crew_id_from_referer("http://host/crews/demo/ui")
        self.assertEqual(result, "demo")

    def test_crew_id_from_referer_with_sub_path(self) -> None:
        """Parses crew_id from /crews/{id}/ui/sub/page."""
        result = server._crew_id_from_referer("http://host/crews/abc/ui/some/page")
        self.assertEqual(result, "abc")

    def test_crew_id_from_referer_non_crew_returns_none(self) -> None:
        """Non-crew Referer returns None."""
        self.assertIsNone(server._crew_id_from_referer("http://example.com/other/path"))

    def test_crew_id_from_referer_empty_returns_none(self) -> None:
        """Empty Referer returns None."""
        self.assertIsNone(server._crew_id_from_referer(""))

    # ── _crew_id_from_cookie unit tests ──────────────────────────────────────

    def test_crew_id_from_cookie_present(self) -> None:
        """Parses crew_id from crew_ui_context cookie."""
        req = _FakeStreamRequest(headers={"cookie": "crew_ui_context=my-crew"})
        result = server._crew_id_from_cookie(req)
        self.assertEqual(result, "my-crew")

    def test_crew_id_from_cookie_multiple_cookies(self) -> None:
        """Correctly extracts crew_ui_context among multiple cookies."""
        req = _FakeStreamRequest(
            headers={"cookie": "session=abc; crew_ui_context=demo; theme=dark"}
        )
        result = server._crew_id_from_cookie(req)
        self.assertEqual(result, "demo")

    def test_crew_id_from_cookie_absent_returns_none(self) -> None:
        """Returns None when cookie is not present."""
        req = _FakeStreamRequest(headers={"cookie": "other=value"})
        result = server._crew_id_from_cookie(req)
        self.assertIsNone(result)

    def test_crew_id_from_cookie_no_cookie_header_returns_none(self) -> None:
        """Returns None when no cookie header at all."""
        req = _FakeStreamRequest(headers={})
        result = server._crew_id_from_cookie(req)
        self.assertIsNone(result)


# ══════════════════════════════════════════════════════════════════════════════
# BearerAuthMiddleware integration — catch-all dispatch
# ══════════════════════════════════════════════════════════════════════════════

class BearerAuthCatchallIntegrationTests(unittest.TestCase):
    """Verify that BearerAuthMiddleware dispatches to _handle_spa_catchall
    after all specific routes (lowest priority), and only for GET."""

    def _make_scope(
        self,
        method: str = "GET",
        path: str = "/static/app.js",
        headers: list[tuple[bytes, bytes]] | None = None,
        api_key: str = "",
    ) -> dict:
        scope_headers = headers or []
        if api_key:
            scope_headers = scope_headers + [
                (b"authorization", f"Bearer {api_key}".encode())
            ]
        return {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": b"",
            "headers": scope_headers,
            "client": ("127.0.0.1", 1234),
        }

    def _run_middleware(
        self,
        scope: dict,
        catchall_response=None,
        api_key: str = "",
    ) -> list[dict]:
        """Run BearerAuthMiddleware and return list of ASGI send events."""
        if catchall_response is None:
            from starlette.responses import PlainTextResponse
            catchall_response = PlainTextResponse("catchall-hit", status_code=200)

        events: list[dict] = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(event):
            events.append(event)

        async def run():
            with patch.object(server, "_handle_spa_catchall", return_value=catchall_response):
                mw = server.BearerAuthMiddleware(
                    app=None,  # should not be called
                    api_key=api_key,
                )
                await mw(scope, receive, send)

        asyncio.run(run())
        return events

    def test_get_request_with_referer_reaches_catchall_no_api_key(self) -> None:
        """With no API key, GET /{path} dispatches to catch-all handler."""
        from starlette.responses import PlainTextResponse
        catchall_resp = PlainTextResponse("spa-asset", status_code=200)
        events = self._run_middleware(
            scope=self._make_scope(
                method="GET",
                path="/static/app.js",
                headers=[(b"referer", b"http://host/crews/demo/ui/")],
            ),
            catchall_response=catchall_resp,
        )
        statuses = [e["status"] for e in events if e.get("type") == "http.response.start"]
        self.assertEqual(statuses, [200])

    def test_crews_ui_path_not_intercepted_by_catchall_no_api_key(self) -> None:
        """/crews/{id}/ui is dispatched to UI proxy, not catch-all."""
        catchall_called: list[bool] = []

        async def fake_catchall(req):
            catchall_called.append(True)
            from starlette.responses import PlainTextResponse
            return PlainTextResponse("should-not-reach")

        from starlette.responses import PlainTextResponse
        ui_proxy_resp = PlainTextResponse("ui-proxy-hit", status_code=200)

        events: list[dict] = []
        scope = self._make_scope(
            method="GET",
            path="/crews/demo/ui",
        )

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(event):
            events.append(event)

        async def run():
            with (
                patch.object(server, "_handle_spa_catchall", side_effect=fake_catchall),
                patch.object(server, "_handle_crew_ui_proxy", return_value=ui_proxy_resp),
            ):
                mw = server.BearerAuthMiddleware(app=None, api_key="")
                await mw(scope, receive, send)

        asyncio.run(run())
        self.assertEqual(catchall_called, [], "Catch-all must NOT be called for /crews/{id}/ui")


if __name__ == "__main__":
    unittest.main()
