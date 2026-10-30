"""Radar microservice — fleet dashboard SPA and browser-facing API.

Serves the Radar SPA from static/ and proxies GET /api/crews to
ga-transport's internal /internal/crews endpoint using the shared
ga-transport-secret. Radar is the only entry point for UI traffic;
browsers never reach ga-transport directly for fleet observability.

Uses starlette directly (no fastapi dependency) so the test venv can import
it without additional deps beyond the transport's own requirements.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

# httpx2 is the httpx-compatible HTTP client used in the ghostship stack.
try:
    import httpx
except ImportError:
    import httpx2 as httpx  # type: ignore[no-redef]

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

logger = logging.getLogger("radar")

# ── Configuration ──────────────────────────────────────────────────────────────

TRANSPORT_URL: str = os.environ.get("TRANSPORT_URL", "http://ga-transport:64057")
_TRANSPORT_SECRET_FILE = "/run/secrets/ga-transport-secret"


def _load_transport_secret() -> str:
    """Read the transport secret from the Podman secret mount at startup."""
    try:
        secret = Path(_TRANSPORT_SECRET_FILE).read_text().strip()
        if secret:
            logger.info("Transport secret loaded from %s", _TRANSPORT_SECRET_FILE)
            return secret
    except FileNotFoundError:
        pass
    logger.warning(
        "Transport secret not found at %s — X-Transport-Token header will be empty",
        _TRANSPORT_SECRET_FILE,
    )
    return ""


_TRANSPORT_SECRET: str = _load_transport_secret()

# ── Handlers ────────────────────────────────────────────────────────────────────

_STATIC_DIR = Path(__file__).parent / "static"


async def health(request: Request) -> JSONResponse:
    """GET /health — no auth required."""
    return JSONResponse({"status": "ok"})


async def api_crews(request: Request) -> Response:
    """GET /api/crews — proxy to ga-transport GET /internal/crews.

    Forwards the X-Transport-Token header so transport's
    TransportSecretMiddleware accepts the request.  Returns 502 with an
    error JSON body if the transport is unreachable or returns an error.
    """
    url = f"{TRANSPORT_URL}/internal/crews"
    headers = {"X-Transport-Token": _TRANSPORT_SECRET}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
    except httpx.RequestError as exc:
        logger.error("Transport unreachable: %s", exc)
        return JSONResponse(
            {"error": "transport unreachable", "detail": str(exc)},
            status_code=502,
        )

    if resp.status_code != 200:
        logger.error(
            "Transport returned %d for %s: %s",
            resp.status_code,
            url,
            resp.text[:200],
        )
        return JSONResponse(
            {"error": "transport error", "status_code": resp.status_code},
            status_code=502,
        )

    return Response(
        content=resp.content,
        status_code=200,
        media_type="application/json",
    )


async def index(request: Request) -> FileResponse:
    """GET / — serve the Radar SPA root (index.html)."""
    return FileResponse(str(_STATIC_DIR / "index.html"), media_type="text/html")


# ── Application ─────────────────────────────────────────────────────────────────

app = Starlette(
    routes=[
        Route("/health", health),
        Route("/api/crews", api_crews),
        Route("/", index),
        Mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static"),
    ],
)
