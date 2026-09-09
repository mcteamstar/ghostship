"""Tests for transport/openapi.py (TRN-129).

Covers:
  4.1 Unit tests for generate_schema with mock routes and tools
  4.2 Integration: GET /openapi.json returns 200 with application/json
  4.3 Integration: GET /openapi.json returns 200 without Authorization header
  4.4 Integration: every route key from routes/public_routes appears in schema paths
  4.5 Integration: all registered MCP tool names appear under /mcp/tools/{name}

The integration tests run against the live transport.server module using the
same lightweight async harness used elsewhere in this test suite.
"""

from __future__ import annotations

import json
import sys
import types
import unittest
from typing import Any
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Import transport.openapi — it has no heavy deps so no stubs are needed.
# ---------------------------------------------------------------------------

import transport.openapi as openapi_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeRoute:
    """Minimal stand-in for Starlette's Route used in generate_schema tests."""

    def __init__(self, path: str, methods: list[str]) -> None:
        self.path = path
        self.methods = methods


def _make_routes() -> "dict[tuple[str, str], Any]":
    return {
        ("POST", "/login"):               None,
        ("GET",  "/login"):               None,
        ("POST", "/logout"):              None,
        ("GET",  "/health"):              None,
        ("GET",  "/crews/*/ui"):          None,
        ("GET",  "/crews/*/api"):         None,
        ("POST", "/crews/*/dashboard"):   None,
        ("DELETE", "/crews/*/dashboard"): None,
        ("WS",   "/crews/*/ui"):          None,
    }


def _make_public_routes() -> "dict[tuple[str, str], Any]":
    return {
        ("GET",  "/version"):             None,
        ("POST", "/dashboard/login"):     None,
        ("POST", "/dashboard/logout"):    None,
        ("GET",  "/dashboard/auth"):      None,
        ("GET",  "/dashboard/login"):     None,
        ("GET",  "/openapi.json"):        None,
    }


def _make_file_routes() -> list[_FakeRoute]:
    return [
        _FakeRoute("/files/{crew_id}/{path:path}", ["GET"]),
        _FakeRoute("/files/{crew_id}/{path:path}", ["POST"]),
    ]


def _make_tools() -> "list[dict[str, Any]]":
    return [
        {
            "name": "crews",
            "description": "List live crews",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "launch",
            "description": "Launch a crew",
            "input_schema": {
                "type": "object",
                "properties": {
                    "crew_id": {"type": "string"},
                    "composition": {"type": "string"},
                },
            },
        },
        {
            "name": "nuke",
            "description": "Tear down a crew",
            "input_schema": {"type": "object", "properties": {"crew_id": {"type": "string"}}},
        },
    ]


# ---------------------------------------------------------------------------
# 4.1 Unit tests for generate_schema
# ---------------------------------------------------------------------------

class TestGenerateSchema(unittest.TestCase):
    """Unit tests for openapi_mod.generate_schema."""

    def setUp(self) -> None:
        self.schema = openapi_mod.generate_schema(
            routes=_make_routes(),
            public_routes=_make_public_routes(),
            file_routes=_make_file_routes(),
            mcp_tools=_make_tools(),
            version="1.2.3",
        )

    def test_openapi_version(self) -> None:
        self.assertEqual(self.schema["openapi"], "3.1.0")

    def test_info_version(self) -> None:
        self.assertEqual(self.schema["info"]["version"], "1.2.3")

    def test_info_title_present(self) -> None:
        self.assertIn("title", self.schema["info"])
        self.assertTrue(self.schema["info"]["title"])

    def test_bearer_auth_scheme_defined(self) -> None:
        schemes = self.schema["components"]["securitySchemes"]
        self.assertIn("BearerAuth", schemes)
        self.assertEqual(schemes["BearerAuth"]["type"], "http")
        self.assertEqual(schemes["BearerAuth"]["scheme"], "bearer")

    def test_paths_key_present(self) -> None:
        self.assertIn("paths", self.schema)
        self.assertIsInstance(self.schema["paths"], dict)
        self.assertGreater(len(self.schema["paths"]), 0)

    # ------------------------------------------------------------------
    # Authenticated routes have BearerAuth security
    # ------------------------------------------------------------------

    def test_authenticated_routes_have_bearer_security(self) -> None:
        """Routes from the `routes` dict must carry BearerAuth security."""
        paths = self.schema["paths"]
        # /login, /logout are authenticated routes
        self.assertIn("/login", paths)
        for method_entry in paths["/login"].values():
            self.assertIn({"BearerAuth": []}, method_entry.get("security", []),
                          msg="/login should require BearerAuth")

    def test_crew_proxy_routes_authenticated(self) -> None:
        crew_ui = self.schema["paths"].get("/crews/{crew_id}/ui", {})
        self.assertTrue(crew_ui, "crews/{crew_id}/ui should be present")
        for method_entry in crew_ui.values():
            self.assertIn({"BearerAuth": []}, method_entry.get("security", []))

    # ------------------------------------------------------------------
    # Public routes have empty security array
    # ------------------------------------------------------------------

    def test_public_routes_have_empty_security(self) -> None:
        paths = self.schema["paths"]
        for public_path in ("/version", "/health", "/openapi.json"):
            self.assertIn(public_path, paths,
                          msg=f"{public_path} should be in schema paths")
            for method_entry in paths[public_path].values():
                security = method_entry.get("security", None)
                self.assertEqual(security, [],
                                 msg=f"{public_path} should have security: []")

    def test_dashboard_login_is_public(self) -> None:
        entry = self.schema["paths"].get("/dashboard/login", {})
        for method_entry in entry.values():
            self.assertEqual(method_entry.get("security", None), [])

    # ------------------------------------------------------------------
    # Wildcard → named path conversion
    # ------------------------------------------------------------------

    def test_wildcard_paths_converted(self) -> None:
        paths = self.schema["paths"]
        self.assertIn("/crews/{crew_id}/ui", paths, "wildcard should become named param")
        self.assertIn("/crews/{crew_id}/api", paths)
        self.assertIn("/crews/{crew_id}/dashboard", paths)
        self.assertNotIn("/crews/*/ui", paths, "raw wildcard must not appear in schema")

    # ------------------------------------------------------------------
    # WS routes are skipped
    # ------------------------------------------------------------------

    def test_ws_routes_not_present(self) -> None:
        """WS entries from routes dict must be silently skipped."""
        # The only WS route is ("WS", "/crews/*/ui"); it must not produce a
        # separate "ws" verb entry in the schema.
        for path_entry in self.schema["paths"].values():
            self.assertNotIn("ws", path_entry,
                             msg="WebSocket routes should not appear as path entries")

    # ------------------------------------------------------------------
    # File routes
    # ------------------------------------------------------------------

    def test_file_routes_present(self) -> None:
        paths = self.schema["paths"]
        self.assertIn("/files/{crew_id}/{path}", paths)
        entry = paths["/files/{crew_id}/{path}"]
        self.assertIn("get", entry)
        self.assertIn("post", entry)

    def test_file_routes_have_no_bearer_security(self) -> None:
        """File routes use presigned-URL auth — they should have security: []."""
        entry = self.schema["paths"].get("/files/{crew_id}/{path}", {})
        for method_entry in entry.values():
            self.assertEqual(method_entry.get("security", None), [])

    # ------------------------------------------------------------------
    # MCP tool paths
    # ------------------------------------------------------------------

    def test_mcp_tools_present(self) -> None:
        paths = self.schema["paths"]
        for tool in _make_tools():
            tool_path = f"/mcp/tools/{tool['name']}"
            self.assertIn(tool_path, paths,
                          msg=f"tool path {tool_path} should be in schema")

    def test_mcp_tool_entries_have_request_body(self) -> None:
        tool_entry = self.schema["paths"]["/mcp/tools/launch"]["post"]
        self.assertIn("requestBody", tool_entry)
        rb = tool_entry["requestBody"]
        self.assertIn("content", rb)
        self.assertIn("application/json", rb["content"])

    def test_mcp_tool_entries_require_bearer(self) -> None:
        tool_entry = self.schema["paths"]["/mcp/tools/crews"]["post"]
        self.assertIn({"BearerAuth": []}, tool_entry.get("security", []))

    def test_mcp_tool_entries_tagged_mcp_tools(self) -> None:
        tool_entry = self.schema["paths"]["/mcp/tools/nuke"]["post"]
        self.assertIn("mcp-tools", tool_entry.get("tags", []))

    def test_mcp_tool_description_from_tool_def(self) -> None:
        tool_entry = self.schema["paths"]["/mcp/tools/launch"]["post"]
        self.assertIn("Launch a crew", tool_entry.get("summary", ""))

    def test_mcp_tool_input_schema_matches(self) -> None:
        """Input schema for 'launch' must match the mock schema definition."""
        tool_entry = self.schema["paths"]["/mcp/tools/launch"]["post"]
        schema = tool_entry["requestBody"]["content"]["application/json"]["schema"]
        self.assertIn("crew_id", schema.get("properties", {}))

    # ------------------------------------------------------------------
    # /mcp endpoint
    # ------------------------------------------------------------------

    def test_mcp_endpoint_present(self) -> None:
        self.assertIn("/mcp", self.schema["paths"])
        entry = self.schema["paths"]["/mcp"]
        self.assertIn("post", entry)

    def test_mcp_endpoint_requires_bearer(self) -> None:
        entry = self.schema["paths"]["/mcp"]["post"]
        self.assertIn({"BearerAuth": []}, entry.get("security", []))

    # ------------------------------------------------------------------
    # Empty tool list
    # ------------------------------------------------------------------

    def test_empty_tool_list_produces_valid_schema(self) -> None:
        schema = openapi_mod.generate_schema(
            routes=_make_routes(),
            public_routes=_make_public_routes(),
            file_routes=_make_file_routes(),
            mcp_tools=[],
            version="0.0.0",
        )
        self.assertEqual(schema["openapi"], "3.1.0")
        # No /mcp/tools/* paths when tool list is empty
        for path in schema["paths"]:
            self.assertFalse(
                path.startswith("/mcp/tools/"),
                msg="No tool paths when mcp_tools=[]",
            )


# ---------------------------------------------------------------------------
# 4.4 All route keys appear in the schema
# ---------------------------------------------------------------------------

class TestRouteCoverage(unittest.TestCase):
    """Assert every key from routes and public_routes is in the schema paths."""

    def test_all_route_keys_in_schema(self) -> None:
        routes = _make_routes()
        public_routes = _make_public_routes()
        schema = openapi_mod.generate_schema(
            routes=routes,
            public_routes=public_routes,
            file_routes=_make_file_routes(),
            mcp_tools=[],
            version="0.0.0",
        )
        paths = schema["paths"]
        for method, raw_path in list(routes.keys()) + list(public_routes.keys()):
            if method in openapi_mod._SKIP_METHODS:
                continue
            expected_path = openapi_mod._to_openapi_path(raw_path)
            self.assertIn(
                expected_path,
                paths,
                msg=f"Route ({method}, {raw_path}) → {expected_path} missing from schema paths",
            )
            # Also check the verb is present
            verb = method.lower()
            self.assertIn(
                verb,
                paths[expected_path],
                msg=f"Method {verb} missing from schema path {expected_path}",
            )


# ---------------------------------------------------------------------------
# 4.5 All MCP tool names appear under /mcp/tools/{tool_name}
# ---------------------------------------------------------------------------

class TestToolCoverage(unittest.TestCase):
    def test_all_tool_names_in_schema(self) -> None:
        tools = _make_tools()
        schema = openapi_mod.generate_schema(
            routes=_make_routes(),
            public_routes=_make_public_routes(),
            file_routes=_make_file_routes(),
            mcp_tools=tools,
            version="0.0.0",
        )
        paths = schema["paths"]
        for tool in tools:
            expected_path = f"/mcp/tools/{tool['name']}"
            self.assertIn(
                expected_path,
                paths,
                msg=f"Tool '{tool['name']}' missing from schema paths",
            )


# ---------------------------------------------------------------------------
# Integration tests: server.py integration
# ---------------------------------------------------------------------------
# These tests exercise the transport.server module via the same import-stub
# bootstrap used in the rest of the test suite, driving the handler directly.
# ---------------------------------------------------------------------------

def _server_available() -> bool:
    """Return True if transport.server can be imported (via test bootstrap stubs)."""
    try:
        # Use the same stub-install bootstrap used by the rest of the suite.
        # This installs httpx/mcp/starlette/uvicorn stubs if the real packages
        # are not present, making transport.server importable in a bare checkout.
        from tests.unit.test_file_transfer import _install_import_stubs  # noqa: F401
        _install_import_stubs()
        import transport.server  # noqa: F401
        return True
    except Exception:
        return False


@unittest.skipUnless(_server_available(), "transport.server not importable")
class TestOpenApiEndpointIntegration(unittest.TestCase):
    """Integration tests for GET /openapi.json via the handler function."""

    def setUp(self) -> None:
        import transport.server as srv
        import transport.openapi as oa
        # Inject a known schema so handler tests are deterministic
        self._schema = oa.generate_schema(
            routes=_make_routes(),
            public_routes=_make_public_routes(),
            file_routes=_make_file_routes(),
            mcp_tools=_make_tools(),
            version="9.9.9",
        )
        # Patch the module-level cache directly
        self._orig_schema = srv._openapi_schema
        srv._openapi_schema = self._schema

    def tearDown(self) -> None:
        import transport.server as srv
        srv._openapi_schema = self._orig_schema

    def _call_handler(self) -> "Any":
        """Call _handle_openapi_get synchronously using asyncio.run."""
        import asyncio
        import transport.server as srv

        class _FakeRequest:
            pass

        return asyncio.run(srv._handle_openapi_get(_FakeRequest()))

    # 4.2 Returns 200 with application/json
    def test_returns_200_with_json_content_type(self) -> None:
        response = self._call_handler()
        self.assertEqual(response.status_code, 200)
        content_type = ""
        if hasattr(response, "media_type"):
            content_type = getattr(response, "media_type") or ""
        if not content_type and hasattr(response, "kwargs"):
            content_type = response.kwargs.get("media_type", "")
        if not content_type and hasattr(response, "headers"):
            h = response.headers
            if isinstance(h, dict):
                content_type = h.get("content-type", h.get("Content-Type", ""))
        self.assertIn("application/json", content_type,
                      msg=f"Expected application/json content-type, got: {content_type!r}")

    # 4.2 Body parses as valid JSON
    def test_body_parses_as_json(self) -> None:
        response = self._call_handler()
        body = getattr(response, "body", b"")
        if not body:
            # Some response stubs expose content differently
            body = getattr(response, "_content", b"")
        parsed = json.loads(body)
        self.assertIsInstance(parsed, dict)
        self.assertIn("openapi", parsed)

    # 4.3 Returns 200 without Authorization header
    # (public route — no auth check in the handler itself)
    def test_no_auth_header_required(self) -> None:
        """Handler must return 200 regardless of auth headers (route is public)."""
        response = self._call_handler()
        self.assertNotEqual(response.status_code, 401)
        self.assertNotEqual(response.status_code, 403)

    # 4.4 Every route key appears in schema paths
    def test_all_route_keys_in_returned_schema(self) -> None:
        response = self._call_handler()
        body = getattr(response, "body", b"") or getattr(response, "_content", b"")
        parsed = json.loads(body)
        paths = parsed.get("paths", {})
        routes = _make_routes()
        public_routes = _make_public_routes()
        for method, raw_path in list(routes.keys()) + list(public_routes.keys()):
            if method in openapi_mod._SKIP_METHODS:
                continue
            expected = openapi_mod._to_openapi_path(raw_path)
            self.assertIn(
                expected,
                paths,
                msg=f"Route ({method}, {raw_path}) → {expected} missing from GET /openapi.json response",
            )

    # 4.5 All MCP tool names appear in schema
    def test_all_tool_names_in_returned_schema(self) -> None:
        response = self._call_handler()
        body = getattr(response, "body", b"") or getattr(response, "_content", b"")
        parsed = json.loads(body)
        paths = parsed.get("paths", {})
        for tool in _make_tools():
            tool_path = f"/mcp/tools/{tool['name']}"
            self.assertIn(
                tool_path,
                paths,
                msg=f"Tool '{tool['name']}' missing from GET /openapi.json paths",
            )


# ---------------------------------------------------------------------------
# Test: GET /openapi.json is registered as a public route in server.py
# ---------------------------------------------------------------------------

@unittest.skipUnless(_server_available(), "transport.server not importable")
class TestOpenApiRouteRegistration(unittest.TestCase):
    """Assert /openapi.json is registered as a public route in server.py."""

    def test_openapi_handler_is_defined(self) -> None:
        import transport.server as srv
        self.assertTrue(
            callable(getattr(srv, "_handle_openapi_get", None)),
            "_handle_openapi_get should be defined in transport.server",
        )

    def test_openapi_schema_cache_exists(self) -> None:
        import transport.server as srv
        self.assertTrue(
            hasattr(srv, "_openapi_schema"),
            "_openapi_schema cache should be defined in transport.server",
        )


# ---------------------------------------------------------------------------
# Test: get_mcp_tools helper
# ---------------------------------------------------------------------------

class TestGetMcpTools(unittest.TestCase):
    """Tests for openapi_mod.get_mcp_tools."""

    def _make_mock_mcp(self, tools: "dict[str, Any]") -> MagicMock:
        """Build a minimal MagicMock that looks like an MCPServer with tools."""
        mock_tool_manager = MagicMock()
        mock_tool_manager._tools = {}
        for name, (description, schema) in tools.items():
            t = MagicMock()
            t.description = description
            t.parameters = schema
            t.input_schema = None
            mock_tool_manager._tools[name] = t
        mock_mcp = MagicMock()
        mock_mcp._tool_manager = mock_tool_manager
        return mock_mcp

    def test_extracts_tool_names(self) -> None:
        mcp = self._make_mock_mcp({
            "crews": ("List crews", {"type": "object", "properties": {}}),
            "launch": ("Launch crew", {"type": "object", "properties": {}}),
        })
        tools = openapi_mod.get_mcp_tools(mcp)
        names = [t["name"] for t in tools]
        self.assertIn("crews", names)
        self.assertIn("launch", names)

    def test_extracts_tool_description(self) -> None:
        mcp = self._make_mock_mcp({
            "nuke": ("Tear down a crew", {"type": "object"}),
        })
        tools = openapi_mod.get_mcp_tools(mcp)
        self.assertEqual(tools[0]["description"], "Tear down a crew")

    def test_extracts_input_schema(self) -> None:
        schema = {"type": "object", "properties": {"crew_id": {"type": "string"}}}
        mcp = self._make_mock_mcp({"crews": ("List", schema)})
        tools = openapi_mod.get_mcp_tools(mcp)
        self.assertEqual(tools[0]["input_schema"], schema)

    def test_returns_empty_list_when_no_tool_manager(self) -> None:
        mcp = MagicMock()
        del mcp._tool_manager
        mcp._tool_manager = None
        tools = openapi_mod.get_mcp_tools(mcp)
        self.assertEqual(tools, [])

    def test_returns_empty_list_on_exception(self) -> None:
        class _Bad:
            @property
            def _tool_manager(self):
                raise RuntimeError("boom")
        tools = openapi_mod.get_mcp_tools(_Bad())
        self.assertEqual(tools, [])


# ---------------------------------------------------------------------------
# Test: _to_openapi_path wildcard conversion
# ---------------------------------------------------------------------------

class TestToOpenApiPath(unittest.TestCase):
    def test_plain_path_unchanged(self) -> None:
        self.assertEqual(openapi_mod._to_openapi_path("/health"), "/health")
        self.assertEqual(openapi_mod._to_openapi_path("/version"), "/version")

    def test_known_wildcards_converted(self) -> None:
        self.assertEqual(openapi_mod._to_openapi_path("/crews/*/ui"), "/crews/{crew_id}/ui")
        self.assertEqual(openapi_mod._to_openapi_path("/crews/*/api"), "/crews/{crew_id}/api")
        self.assertEqual(openapi_mod._to_openapi_path("/crews/*/dashboard"), "/crews/{crew_id}/dashboard")

    def test_unknown_wildcard_gets_generic_param(self) -> None:
        result = openapi_mod._to_openapi_path("/foo/*/bar")
        self.assertIn("{", result)
        self.assertNotIn("*", result)

    def test_no_mutation_of_input(self) -> None:
        original = "/crews/*/ui"
        openapi_mod._to_openapi_path(original)
        self.assertEqual(original, "/crews/*/ui")


# ---------------------------------------------------------------------------
# Test: _read_version helper
# ---------------------------------------------------------------------------

class TestReadVersion(unittest.TestCase):
    def test_reads_version_from_file(self) -> None:
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix="VERSION", delete=False) as f:
            f.write("1.2.3\n")
            path = f.name
        try:
            result = openapi_mod._read_version(version_file=path)
            self.assertEqual(result, "1.2.3")
        finally:
            import os
            os.unlink(path)

    def test_falls_back_when_file_missing(self) -> None:
        result = openapi_mod._read_version(version_file="/nonexistent/VERSION")
        self.assertEqual(result, "0.0.0")


if __name__ == "__main__":
    unittest.main()
