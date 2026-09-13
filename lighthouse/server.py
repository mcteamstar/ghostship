"""ga-lighthouse — fleet observability server (TRN-97).

A small Starlette application that:

- Serves the vanilla-JS single-page fleet dashboard from ``./static/``.
- Proxies ``/api/*`` to ``ga-transport`` over ``ga-portside``, adding the
  ``X-Transport-Token`` header (and, when configured, a ``Authorization:
  Bearer`` header) server-side so the browser never sees either secret.
- Exposes ``/healthz`` for the compose healthcheck.

Secrets are read from mounted Podman secret files at startup:

    /run/secrets/ga-transport-secret   → X-Transport-Token on every /api call
    /run/secrets/ga-api-key            → Bearer token (optional; empty if absent)

The transport token is NEVER injected into the served HTML — only the API key
(user-facing Bearer token) is, and only when it is non-empty.

httpx2 (not httpx) — consistent with the transport and TRN-155.
"""

from __future__ import annotations

import logging
import os

import httpx2 as httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
)
from starlette.routing import Route

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ga-lighthouse")

# ── Configuration ─────────────────────────────────────────────────────────────

TRANSPORT_URL = os.environ.get("TRANSPORT_URL", "http://ga-transport:64057").rstrip("/")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# Per-request hard timeout when proxying to the transport.
_PROXY_TIMEOUT_SECS = 10.0


def _read_secret(path: str, default: str = "") -> str:
    """Read a mounted Podman secret file, returning ``default`` if absent."""
    try:
        with open(path) as fh:
            return fh.read().strip()
    except FileNotFoundError:
        return default
    except OSError:
        return default


TRANSPORT_TOKEN = _read_secret("/run/secrets/ga-transport-secret")
API_KEY = _read_secret("/run/secrets/ga-api-key")

if not TRANSPORT_TOKEN:
    logger.warning(
        "ga-transport-secret is empty or absent — /api/* calls will fail the "
        "transport's X-Transport-Token check"
    )


# ── Static SPA serving ──────────────────────────────────────────────────────

def _render_index() -> str:
    """Load index.html and inject the API key template variable.

    ``__API_KEY__`` in the template is replaced with the API key value when it
    is non-empty (so the SPA can send it as a Bearer token), or an empty string
    otherwise. The transport token is deliberately NOT injected.
    """
    index_path = os.path.join(STATIC_DIR, "index.html")
    with open(index_path, encoding="utf-8") as fh:
        html = fh.read()
    return html.replace("__API_KEY__", API_KEY)


async def _handle_index(request: Request) -> Response:
    """GET / — serve the fleet dashboard SPA with the API key injected."""
    try:
        return HTMLResponse(_render_index())
    except FileNotFoundError:
        return PlainTextResponse("index.html not found", status_code=500)


async def _handle_static(request: Request) -> Response:
    """GET /static/{path} — serve a static asset (CSS, etc.)."""
    rel = request.path_params.get("path", "")
    # Prevent path traversal — resolve and confirm it stays under STATIC_DIR.
    full = os.path.normpath(os.path.join(STATIC_DIR, rel))
    if not full.startswith(STATIC_DIR + os.sep) and full != STATIC_DIR:
        return PlainTextResponse("Not found", status_code=404)
    if not os.path.isfile(full):
        return PlainTextResponse("Not found", status_code=404)
    media_type = "text/plain"
    if full.endswith(".css"):
        media_type = "text/css"
    elif full.endswith(".js"):
        media_type = "application/javascript"
    elif full.endswith(".html"):
        media_type = "text/html"
    with open(full, "rb") as fh:
        return Response(fh.read(), media_type=media_type)


# ── /api/* transport proxy ────────────────────────────────────────────────────

async def _handle_api_proxy(request: Request) -> Response:
    """GET /api/{path} — proxy to the transport, adding auth headers server-side.

    Adds ``X-Transport-Token`` on every outbound request. When an API key is
    configured, also adds ``Authorization: Bearer <API_KEY>``. The upstream
    status code and body are relayed back to the browser unchanged.
    """
    sub_path = request.path_params.get("path", "")
    upstream = f"{TRANSPORT_URL}/api/{sub_path}"
    query = request.scope.get("query_string", b"").decode("latin-1")
    if query:
        upstream = f"{upstream}?{query}"

    headers = {"X-Transport-Token": TRANSPORT_TOKEN}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    try:
        async with httpx.AsyncClient(timeout=_PROXY_TIMEOUT_SECS) as client:
            upstream_resp = await client.get(upstream, headers=headers)
    except Exception as exc:  # transport unreachable / timeout
        logger.warning("proxy to %s failed: %s", upstream, exc)
        return JSONResponse(
            {"error": "transport unreachable"}, status_code=502
        )

    # Relay body + status. Content-type is preserved when present.
    media_type = upstream_resp.headers.get("content-type", "application/json")
    return Response(
        upstream_resp.content,
        status_code=upstream_resp.status_code,
        media_type=media_type,
    )


# ── Health ─────────────────────────────────────────────────────────────────

async def _handle_healthz(request: Request) -> Response:
    """GET /healthz — liveness probe for the compose healthcheck."""
    return JSONResponse({"status": "ok"})


# ── Application ────────────────────────────────────────────────────────────

app = Starlette(
    routes=[
        Route("/", _handle_index, methods=["GET"]),
        Route("/healthz", _handle_healthz, methods=["GET"]),
        Route("/api/{path:path}", _handle_api_proxy, methods=["GET"]),
        Route("/static/{path:path}", _handle_static, methods=["GET"]),
    ]
)
