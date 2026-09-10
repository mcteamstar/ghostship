#!/usr/bin/env python3
"""Generate the GhostShip transport OpenAPI schema and write it to disk.

This script imports ``transport.openapi`` directly — no running transport
process required.  It reconstructs the route tables from the same source of
truth used at runtime (server.py), calls ``generate_schema``, and writes the
result to ``openapi.json`` at the repository root (or a custom ``--output``
path).

Usage
-----
    python scripts/generate_openapi.py
    python scripts/generate_openapi.py --output /tmp/openapi.json

Designed to be run in CI to capture the schema as a build artefact and
surface diffs in PRs.  Exit code 0 on success, non-zero on any error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Make sure the transport package is importable whether we are running from
# the repo root, from the scripts/ directory, or from a flat /app layout
# (container).  We try three different sys.path configurations.
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _ensure_importable() -> None:
    """Add transport/ parent to sys.path so the package can be imported."""
    candidates = [
        str(_REPO_ROOT),         # repo root — gives `import transport.openapi`
        str(_REPO_ROOT / "transport"),  # flat layout — gives `import openapi`
    ]
    for candidate in candidates:
        if candidate not in sys.path:
            sys.path.insert(0, candidate)


_ensure_importable()


def _import_openapi():
    """Import the openapi module, trying both package and flat layouts."""
    try:
        from transport import openapi  # type: ignore[import]
        return openapi
    except ModuleNotFoundError:
        pass
    try:
        import openapi  # type: ignore[import]  # flat /app/ layout
        return openapi
    except ModuleNotFoundError as exc:
        raise SystemExit(
            f"ERROR: could not import transport.openapi — {exc}\n"
            "Make sure you are running this script from the repository root."
        ) from exc


# ---------------------------------------------------------------------------
# Route tables — must mirror server.py's BearerAuthMiddleware constructor.
# We use None as a placeholder for the handler callables: generate_schema
# only iterates the keys (method, path), not the values.
# ---------------------------------------------------------------------------

_ROUTES: dict[tuple[str, str], None] = {
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

_PUBLIC_ROUTES: dict[tuple[str, str], None] = {
    ("GET",  "/version"):             None,
    ("POST", "/dashboard/login"):     None,
    ("POST", "/dashboard/logout"):    None,
    ("GET",  "/dashboard/auth"):      None,
    ("GET",  "/dashboard/login"):     None,
    ("GET",  "/openapi.json"):        None,
}


class _FakeRoute:
    """Minimal stand-in for a Starlette Route with .path and .methods."""

    def __init__(self, path: str, methods: list[str]) -> None:
        self.path = path
        self.methods = methods


_FILE_ROUTES: list[_FakeRoute] = [
    _FakeRoute("/files/{crew_id}/{path:path}", ["GET"]),
    _FakeRoute("/files/{crew_id}/{path:path}", ["POST"]),
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate the GhostShip transport OpenAPI schema."
    )
    parser.add_argument(
        "--output",
        default=str(_REPO_ROOT / "openapi.json"),
        help="Path to write the generated schema (default: <repo-root>/openapi.json)",
    )
    args = parser.parse_args()

    openapi_mod = _import_openapi()

    # Read version from the VERSION file (no server startup required)
    version = openapi_mod._read_version()

    # No MCP instance available at build time — produce an empty tool list.
    # The schema will document all HTTP routes; tool entries can be populated
    # by running this script inside the container where the MCP server runs.
    mcp_tools: list[dict] = []

    schema = openapi_mod.generate_schema(
        routes=_ROUTES,
        public_routes=_PUBLIC_ROUTES,
        file_routes=_FILE_ROUTES,
        mcp_tools=mcp_tools,
        version=version,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(schema, indent=2) + "\n")

    print(f"OpenAPI schema written to {output_path}")
    print(f"  openapi: {schema['openapi']}")
    print(f"  version: {schema['info']['version']}")
    print(f"  paths:   {len(schema.get('paths', {}))} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
