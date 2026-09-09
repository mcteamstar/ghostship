"""OpenAPI 3.1.0 schema generation for the GhostShip transport.

This module is the single place where the transport's HTTP surface is turned
into a machine-readable OpenAPI document.  It is deliberately free of I/O and
side effects: ``generate_schema`` is a pure function that takes the route
tables and an MCP tool list and returns a plain Python dict.  ``server.py``
calls it once at startup and caches the result.

Usage
-----
    from transport.openapi import generate_schema, get_mcp_tools

    tools = get_mcp_tools(mcp)          # extract tools from the MCPServer
    schema = generate_schema(
        routes=routes,
        public_routes=public_routes,
        file_routes=file_routes,        # Starlette Route list from files.py
        mcp_tools=tools,
        version=TRANSPORT_VERSION,
    )
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Wildcard-path lookup table (task 1.3)
# Maps the raw wildcard path strings used as route-dict keys in server.py to
# their corresponding OpenAPI path-template strings with named parameters.
# Every entry here must match a route key actually registered in BearerAuthMiddleware.
# New wildcard routes added in future must be added here too — the CI schema
# coverage test will catch any gap.
# ---------------------------------------------------------------------------

_WILDCARD_PATH_MAP: dict[str, str] = {
    "/crews/*/ui":        "/crews/{crew_id}/ui",
    "/crews/*/api":       "/crews/{crew_id}/api",
    "/crews/*/dashboard": "/crews/{crew_id}/dashboard",
}

# Methods that are surfaced in the schema for wildcard routes.
# WS routes are documented as a note, not as a full path entry (see design).
_SKIP_METHODS = {"WS"}


# ---------------------------------------------------------------------------
# MCP tool extraction helper (task 1.5)
# ---------------------------------------------------------------------------

def get_mcp_tools(mcp: Any) -> list[dict[str, Any]]:
    """Extract tool metadata from an MCPServer instance.

    Accesses the internal tool manager synchronously — tools are registered at
    import time, not lazily, so no event loop is required.  Wraps the access
    in one place so there is a single spot to update when/if FastMCP adds a
    public sync API.

    Returns a list of dicts, each with:
        ``name``        — tool name (str)
        ``description`` — docstring-derived description (str)
        ``input_schema``— JSON Schema dict for the tool's input model
    """
    tools: list[dict[str, Any]] = []

    # FastMCP / MCPServer exposes tools via the internal _tool_manager.
    # The manager's _tools attribute is a dict[str, Tool]; each Tool has
    # .name, .description, and .parameters (a JSON Schema dict).
    try:
        tool_manager = getattr(mcp, "_tool_manager", None)
        if tool_manager is None:
            return tools
        raw_tools = getattr(tool_manager, "_tools", None)
        if raw_tools is None:
            # Older SDK versions store tools directly on the manager
            raw_tools = getattr(tool_manager, "tools", {})
        for tool_name, tool_obj in raw_tools.items():
            description = getattr(tool_obj, "description", "") or ""
            # input_schema may be stored as .parameters or .input_schema
            input_schema = (
                getattr(tool_obj, "parameters", None)
                or getattr(tool_obj, "input_schema", None)
                or {"type": "object", "properties": {}}
            )
            tools.append({
                "name": tool_name,
                "description": description,
                "input_schema": input_schema,
            })
    except Exception:
        # Fail gracefully — the schema is still valid without tool entries
        pass

    return tools


# ---------------------------------------------------------------------------
# Path conversion helpers
# ---------------------------------------------------------------------------

def _to_openapi_path(raw_path: str) -> str:
    """Convert a raw route path (possibly with * wildcards) to an OpenAPI path template.

    Uses the hardcoded lookup table for known wildcard routes; falls back to a
    generic ``{param}`` substitution for any unknown wildcard so that at least
    something appears in the schema (the CI coverage test will surface the gap).
    """
    if "*" not in raw_path:
        return raw_path
    mapped = _WILDCARD_PATH_MAP.get(raw_path)
    if mapped:
        return mapped
    # Fallback: replace each * with a positional generic name
    parts = raw_path.split("/")
    counter = [0]

    def _replace(p: str) -> str:
        if p == "*":
            counter[0] += 1
            return "{param" + str(counter[0]) + "}"
        return p

    # Skip the leading empty string that split("/") produces for "/..." paths;
    # the prepended "/" already provides the leading slash.
    return "/" + "/".join(_replace(p) for p in parts[1:])


def _path_description(method: str, path: str, is_public: bool) -> str:
    """Return a brief human-readable description for a route."""
    _descriptions: dict[tuple[str, str], str] = {
        ("GET",    "/health"):                  "Health check — always public",
        ("POST",   "/login"):                   "Initiate login / exchange credentials for session",
        ("GET",    "/login"):                   "Login page (UI redirect)",
        ("POST",   "/logout"):                  "Invalidate the current session",
        ("GET",    "/version"):                 "Transport version (public)",
        ("GET",    "/openapi.json"):            "This OpenAPI schema (public)",
        ("POST",   "/dashboard/login"):         "Dashboard login — exchange API key for session cookie",
        ("POST",   "/dashboard/logout"):        "Dashboard logout — revoke session cookie",
        ("GET",    "/dashboard/auth"):          "Dashboard auth check — returns 200 if session is valid",
        ("GET",    "/dashboard/login"):         "Dashboard login UI page",
        ("GET",    "/crews/{crew_id}/ui"):      "Proxy HTTP requests to a crew's dashboard UI",
        ("GET",    "/crews/{crew_id}/api"):     "Proxy HTTP requests to a crew's MCP/API gateway",
        ("POST",   "/crews/{crew_id}/dashboard"): "Create or refresh a per-crew dashboard session",
        ("DELETE", "/crews/{crew_id}/dashboard"): "Destroy a per-crew dashboard session",
        ("GET",    "/files/{crew_id}/{path}"):  "Download a file from a crew workspace (presigned-URL auth)",
        ("POST",   "/files/{crew_id}/{path}"):  "Upload a file to a crew workspace (presigned-URL auth)",
        ("POST",   "/mcp"):                     "MCP Streamable-HTTP endpoint (requires Bearer auth)",
    }
    key = (method, _to_openapi_path(path) if "*" in path else path)
    return _descriptions.get(key, f"{method} {path}")


# ---------------------------------------------------------------------------
# Core schema generator (tasks 1.1 – 1.7)
# ---------------------------------------------------------------------------

def generate_schema(
    routes: "dict[tuple[str, str], Any]",
    public_routes: "dict[tuple[str, str], Any]",
    file_routes: "list[Any]",
    mcp_tools: "list[dict[str, Any]]",
    version: str = "0.0.0",
) -> dict[str, Any]:
    """Generate an OpenAPI 3.1.0 schema dict from the transport's live route tables.

    Parameters
    ----------
    routes:
        Authenticated route dict ``{(method, path): handler}`` from
        BearerAuthMiddleware — these require a Bearer token.
    public_routes:
        Public route dict ``{(method, path): handler}`` — no auth required.
    file_routes:
        Starlette ``Route`` list from ``transport.files.file_routes``.  Each
        entry has ``.path`` (Starlette path template) and ``.methods`` (set).
    mcp_tools:
        Tool metadata list produced by :func:`get_mcp_tools`.
    version:
        Transport version string (from VERSION file).

    Returns
    -------
    dict
        A valid OpenAPI 3.1.0 document as a plain Python dict, ready for
        ``json.dumps``.
    """

    paths: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Helper: add one path+method entry
    # ------------------------------------------------------------------
    def _add_entry(
        method: str,
        raw_path: str,
        *,
        is_public: bool,
        summary: str = "",
        tags: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if method in _SKIP_METHODS:
            return
        oa_path = _to_openapi_path(raw_path)
        if oa_path not in paths:
            paths[oa_path] = {}
        verb = method.lower()
        entry: dict[str, Any] = {
            "summary": summary or _path_description(method, raw_path, is_public),
            "tags": tags or [_default_tag(raw_path)],
            "responses": {
                "200": {"description": "Success"},
            },
        }
        if not is_public:
            entry["security"] = [{"BearerAuth": []}]
        else:
            entry["security"] = []
        if extra:
            entry.update(extra)
        paths[oa_path][verb] = entry

    # ------------------------------------------------------------------
    # 1. Authenticated routes (Bearer required)
    # ------------------------------------------------------------------
    for (method, raw_path) in routes:
        _add_entry(method, raw_path, is_public=False)

    # ------------------------------------------------------------------
    # 2. Public routes (no auth)
    # ------------------------------------------------------------------
    for (method, raw_path) in public_routes:
        _add_entry(method, raw_path, is_public=True)

    # ------------------------------------------------------------------
    # 3. Hard-coded public paths that live in BearerAuthMiddleware._PUBLIC_PATHS
    #    (/health) — they bypass auth entirely and are not in either dict.
    # ------------------------------------------------------------------
    _add_entry("GET", "/health", is_public=True)

    # ------------------------------------------------------------------
    # 4. File transfer routes (presigned-URL auth — not Bearer)
    # ------------------------------------------------------------------
    for route in file_routes:
        starlette_path = getattr(route, "path", "")
        methods = getattr(route, "methods", None) or {"GET"}
        # Convert Starlette {path:path} style to plain OpenAPI {path}
        oa_path = starlette_path.replace("{path:path}", "{path}")
        if oa_path not in paths:
            paths[oa_path] = {}
        for method in methods:
            verb = method.lower()
            if verb in paths[oa_path]:
                continue
            description = (
                "Download a file from a crew workspace (presigned-URL auth)"
                if method == "GET"
                else "Upload a file to a crew workspace (presigned-URL auth)"
            )
            paths[oa_path][verb] = {
                "summary": description,
                "tags": ["file-transfer"],
                "security": [],   # presigned-URL auth, not Bearer
                "responses": {
                    "200": {"description": "Success"},
                    "401": {"description": "Missing or invalid presigned token"},
                    "403": {"description": "Token expired or path mismatch"},
                },
            }

    # ------------------------------------------------------------------
    # 5. MCP endpoint (handled by the inner mcp_app, not in route dicts)
    # ------------------------------------------------------------------
    _add_entry(
        "POST", "/mcp",
        is_public=False,
        summary="MCP Streamable-HTTP endpoint (requires Bearer auth)",
        tags=["mcp"],
    )

    # ------------------------------------------------------------------
    # 6. /openapi.json itself (task 2.3 registers it as public; add here for
    #    completeness so the schema is self-describing)
    # ------------------------------------------------------------------
    _add_entry(
        "GET", "/openapi.json",
        is_public=True,
        summary="This OpenAPI schema document (public)",
        tags=["meta"],
    )

    # ------------------------------------------------------------------
    # 7. MCP tools as synthetic POST /mcp/tools/{tool_name} (task 1.6)
    # ------------------------------------------------------------------
    for tool in mcp_tools:
        tool_name = tool.get("name", "")
        if not tool_name:
            continue
        tool_path = f"/mcp/tools/{tool_name}"
        if tool_path not in paths:
            paths[tool_path] = {}
        input_schema = tool.get("input_schema") or {"type": "object", "properties": {}}
        paths[tool_path]["post"] = {
            "summary": tool.get("description", f"Invoke the '{tool_name}' MCP tool"),
            "tags": ["mcp-tools"],
            "description": (
                "**Note:** This path is a documentation convention only. "
                "MCP tools are invoked over the MCP Streamable-HTTP protocol "
                f"at `POST /mcp`, not at this path. Tool name: `{tool_name}`."
            ),
            "security": [{"BearerAuth": []}],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": input_schema,
                    }
                },
            },
            "responses": {
                "200": {"description": "Tool result"},
                "400": {"description": "Invalid input"},
            },
        }

    # ------------------------------------------------------------------
    # 8. Assemble top-level schema (task 1.7)
    # ------------------------------------------------------------------
    schema: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": "GhostShip Transport API",
            "version": version,
            "description": (
                "HTTP surface of the GhostShip transport process. "
                "Covers all REST routes, the MCP Streamable-HTTP endpoint, "
                "file transfer routes, and the MCP tool surface. "
                "Served at `GET /openapi.json` — this document is the "
                "authoritative reference for the transport's public interface."
            ),
        },
        "components": {
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": (
                        "Static API key configured via GA_API_KEY. "
                        "Pass as `Authorization: Bearer <key>`."
                    ),
                }
            }
        },
        "tags": [
            {"name": "auth",          "description": "Login, logout, and auth routes"},
            {"name": "crew-proxy",    "description": "Per-crew UI, API, and dashboard proxy routes"},
            {"name": "file-transfer", "description": "File upload/download routes (presigned-URL auth)"},
            {"name": "health",        "description": "Health and version endpoints"},
            {"name": "mcp",           "description": "MCP Streamable-HTTP endpoint"},
            {"name": "mcp-tools",     "description": "MCP tool surface (documentation convention — served via /mcp)"},
            {"name": "meta",          "description": "Schema and metadata endpoints"},
        ],
        "paths": paths,
    }

    return schema


# ---------------------------------------------------------------------------
# Tag inference
# ---------------------------------------------------------------------------

def _default_tag(raw_path: str) -> str:
    """Infer a tag from a raw route path."""
    if raw_path.startswith("/crews/"):
        return "crew-proxy"
    if raw_path.startswith("/files/"):
        return "file-transfer"
    if raw_path in ("/login", "/logout"):
        return "auth"
    if raw_path.startswith("/dashboard/"):
        return "auth"
    if raw_path in ("/health", "/version"):
        return "health"
    if raw_path == "/mcp":
        return "mcp"
    if raw_path.startswith("/mcp/"):
        return "mcp-tools"
    if raw_path == "/openapi.json":
        return "meta"
    return "transport"


# ---------------------------------------------------------------------------
# Version helper (used by build-time script)
# ---------------------------------------------------------------------------

def _read_version(version_file: str | None = None) -> str:
    """Read the transport version from the VERSION file.

    Searches the repo root relative to this module's location.
    Falls back to ``"0.0.0"`` if the file is not found.
    """
    if version_file is None:
        # transport/openapi.py → transport/ → repo root
        here = Path(__file__).resolve().parent
        candidates = [
            here.parent / "VERSION",       # repo root
            here / "VERSION",              # transport/ itself (container layout)
        ]
    else:
        candidates = [Path(version_file)]

    for p in candidates:
        try:
            text = p.read_text().strip()
            if text:
                return text
        except OSError:
            pass
    return "0.0.0"
