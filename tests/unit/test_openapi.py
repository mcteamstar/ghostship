"""Unit tests for transport/openapi.py — schema generation helpers.

Covers:
- ``TestToOpenApiPath``   — wildcard → OpenAPI template conversion
- ``TestDefaultTag``      — tag inference for known and unknown paths
- ``TestGenerateSchema``  — round-trip: stub routes dict → valid OpenAPI 3.1 doc
"""

from __future__ import annotations

import unittest

try:
    import openapi as _openapi
except ModuleNotFoundError:
    from transport import openapi as _openapi


# ── TestToOpenApiPath ─────────────────────────────────────────────────────────


class TestToOpenApiPath(unittest.TestCase):
    """_to_openapi_path: raw paths and wildcard substitution."""

    def test_static_path_unchanged(self):
        self.assertEqual(_openapi._to_openapi_path("/health"), "/health")

    def test_static_nested_path_unchanged(self):
        self.assertEqual(_openapi._to_openapi_path("/dashboard/login"), "/dashboard/login")

    def test_known_wildcard_crew_ui(self):
        self.assertEqual(_openapi._to_openapi_path("/crews/*/ui"), "/crews/{crew_id}/ui")

    def test_known_wildcard_crew_api(self):
        self.assertEqual(_openapi._to_openapi_path("/crews/*/api"), "/crews/{crew_id}/api")

    def test_known_wildcard_crew_dashboard(self):
        self.assertEqual(_openapi._to_openapi_path("/crews/*/dashboard"), "/crews/{crew_id}/dashboard")

    def test_unknown_wildcard_falls_back_to_generic_param(self):
        result = _openapi._to_openapi_path("/unknown/*/path")
        self.assertIn("{", result)
        self.assertIn("}", result)
        # Should not contain literal '*'
        self.assertNotIn("*", result)

    def test_multiple_wildcards_produce_distinct_params(self):
        result = _openapi._to_openapi_path("/a/*/b/*")
        # Two wildcards → two distinct {param1} and {param2}
        self.assertIn("{param1}", result)
        self.assertIn("{param2}", result)


# ── TestDefaultTag ────────────────────────────────────────────────────────────


class TestDefaultTag(unittest.TestCase):
    """_default_tag: known paths and unknown paths."""

    def test_health_path(self):
        self.assertEqual(_openapi._default_tag("/health"), "health")

    def test_version_path(self):
        self.assertEqual(_openapi._default_tag("/version"), "health")

    def test_login_path(self):
        self.assertEqual(_openapi._default_tag("/login"), "auth")

    def test_logout_path(self):
        self.assertEqual(_openapi._default_tag("/logout"), "auth")

    def test_dashboard_path(self):
        self.assertEqual(_openapi._default_tag("/dashboard/login"), "auth")

    def test_crews_path(self):
        self.assertEqual(_openapi._default_tag("/crews/*/ui"), "crew-proxy")

    def test_files_path(self):
        self.assertEqual(_openapi._default_tag("/files/crew/file.txt"), "file-transfer")

    def test_mcp_root(self):
        self.assertEqual(_openapi._default_tag("/mcp"), "mcp")

    def test_mcp_tools_path(self):
        self.assertEqual(_openapi._default_tag("/mcp/tools/my-tool"), "mcp-tools")

    def test_openapi_json_path(self):
        self.assertEqual(_openapi._default_tag("/openapi.json"), "meta")

    def test_unknown_path_returns_transport(self):
        self.assertEqual(_openapi._default_tag("/some/unknown/route"), "transport")


# ── TestGenerateSchema ────────────────────────────────────────────────────────


class _FakeRoute:
    """Minimal Starlette Route substitute for generate_schema file_routes."""

    def __init__(self, path: str, methods: set[str]):
        self.path = path
        self.methods = methods


class TestGenerateSchema(unittest.TestCase):
    """generate_schema round-trip: stub routes → valid OpenAPI 3.1 doc."""

    def _schema(self, routes=None, public_routes=None, file_routes=None, mcp_tools=None, version="1.2.3"):
        return _openapi.generate_schema(
            routes=routes or {},
            public_routes=public_routes or {},
            file_routes=file_routes or [],
            mcp_tools=mcp_tools or [],
            version=version,
        )

    def test_top_level_openapi_field(self):
        schema = self._schema()
        self.assertEqual(schema["openapi"], "3.1.0")

    def test_info_field_present(self):
        schema = self._schema()
        self.assertIn("info", schema)

    def test_paths_field_present(self):
        schema = self._schema()
        self.assertIn("paths", schema)

    def test_version_propagated(self):
        schema = self._schema(version="9.8.7")
        self.assertEqual(schema["info"]["version"], "9.8.7")

    def test_authenticated_route_in_paths(self):
        schema = self._schema(routes={("GET", "/version"): None})
        self.assertIn("/version", schema["paths"])

    def test_public_route_in_paths(self):
        schema = self._schema(public_routes={("GET", "/health"): None})
        self.assertIn("/health", schema["paths"])

    def test_health_is_always_included(self):
        """generate_schema always emits GET /health regardless of routes dicts."""
        schema = self._schema()
        self.assertIn("/health", schema["paths"])

    def test_file_route_in_paths(self):
        fake_route = _FakeRoute("/files/{crew_id}/{path:path}", {"GET", "POST"})
        schema = self._schema(file_routes=[fake_route])
        self.assertIn("/files/{crew_id}/{path}", schema["paths"])

    def test_mcp_endpoint_included(self):
        schema = self._schema()
        self.assertIn("/mcp", schema["paths"])

    def test_openapi_json_included(self):
        schema = self._schema()
        self.assertIn("/openapi.json", schema["paths"])

    def test_authenticated_route_has_security(self):
        schema = self._schema(routes={("GET", "/version"): None})
        entry = schema["paths"]["/version"]["get"]
        self.assertIn("security", entry)
        self.assertNotEqual(entry["security"], [])

    def test_public_route_has_empty_security(self):
        schema = self._schema(public_routes={("GET", "/health"): None})
        entry = schema["paths"]["/health"]["get"]
        self.assertEqual(entry["security"], [])

    def test_mcp_tool_synthetic_path(self):
        tools = [{"name": "my-tool", "description": "A test tool", "input_schema": {"type": "object", "properties": {}}}]
        schema = self._schema(mcp_tools=tools)
        self.assertIn("/mcp/tools/my-tool", schema["paths"])

    def test_components_security_schemes(self):
        schema = self._schema()
        self.assertIn("components", schema)
        self.assertIn("securitySchemes", schema["components"])
        self.assertIn("BearerAuth", schema["components"]["securitySchemes"])

    def test_wildcard_routes_converted(self):
        schema = self._schema(routes={("GET", "/crews/*/ui"): None})
        self.assertIn("/crews/{crew_id}/ui", schema["paths"])
        self.assertNotIn("/crews/*/ui", schema["paths"])


if __name__ == "__main__":
    unittest.main()
