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
import re
from pathlib import Path
from urllib.parse import urlsplit

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


async def api_crew_agents(request: Request) -> Response:
    """GET /api/crews/{crew_id}/agents — proxy to ga-transport per-crew agents endpoint (TRN-304).

    Forwards the X-Transport-Token header to transport's
    ``GET /internal/crews/{crew_id}/agents`` endpoint.  Returns 502 on any
    transport error; passes through the ``{"agents": [...]}`` payload on
    success.
    """
    crew_id = request.path_params.get("crew_id", "")
    url = f"{TRANSPORT_URL}/internal/crews/{crew_id}/agents"
    headers = {"X-Transport-Token": _TRANSPORT_SECRET}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
    except httpx.RequestError as exc:
        logger.error("Transport unreachable for crew agents %s: %s", crew_id, exc)
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


async def api_crew_mail_subjects(request: Request) -> Response:
    """GET /api/crews/{crew_id}/mail-subjects — proxy to transport mailbox subjects (TRN-370).

    Forwards the X-Transport-Token header to transport's
    ``GET /internal/crews/{crew_id}/mail-subjects`` endpoint.  Subject strings
    only are returned.  Any transport failure, including an unreadable mailbox
    source (transport 503), becomes a 502 so the browser shows the crew's
    mailboxes as unavailable rather than empty.
    """
    crew_id = request.path_params.get("crew_id", "")
    url = f"{TRANSPORT_URL}/internal/crews/{crew_id}/mail-subjects"
    headers = {"X-Transport-Token": _TRANSPORT_SECRET}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
    except httpx.RequestError as exc:
        logger.error("Transport unreachable for crew mail subjects %s: %s", crew_id, exc)
        return JSONResponse(
            {"error": "transport unreachable"},
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


# Crew ids are lowercase alphanumerics and interior hyphens, at most 50 characters
# (the same rule the transport enforces at launch). Checking it before building
# the upstream URL keeps a browser-supplied path segment from rewriting the
# transport path it is proxied to.
_CREW_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,48}[a-z0-9]$|^[a-z0-9]$")

# The refresh checks the stored profile, compares the container and may exec into
# it, behind the credential lock; allow longer than a read-only fleet query.
_AUTH_REFRESH_TIMEOUT_SECS = 30.0


def _is_same_origin(request: Request) -> bool:
    """True when the request carries exactly one ``Origin`` naming its own host.

    Radar's session gate validates only the ``gs_session`` cookie, which is
    ``SameSite=Lax`` and so still accompanies same-site requests from other
    pages. A state-changing route therefore also requires the browser's
    ``Origin`` to match the ``Host`` the request was made to. Browsers always
    send ``Origin`` on a ``fetch`` POST and scripts cannot set or alter it, so
    the SPA needs no token and a request without one (or from another origin)
    is refused. Caddy passes ``Host`` through unchanged.
    """
    origins = request.headers.getlist("origin")
    hosts = request.headers.getlist("host")
    if len(origins) != 1 or len(hosts) != 1:
        return False
    try:
        origin = urlsplit(origins[0])
    except ValueError:
        return False
    if (
        origin.scheme not in ("http", "https")
        or not origin.netloc
        or origin.path
        or origin.query
        or origin.fragment
    ):
        return False
    return origin.netloc.lower() == hosts[0].strip().lower()


async def api_crew_auth_refresh(request: Request) -> Response:
    """POST /api/crews/{crew_id}/auth/refresh — proxy to transport's credential refresh (TRN-367).

    The browser-facing half of the per-crew "Refresh auth" action. The request
    must carry a same-origin ``Origin`` (see ``_is_same_origin``); anything else
    is a 403 and transport is not called. Otherwise this forwards to
    ``POST /internal/crews/{crew_id}/auth/refresh`` with ``X-Transport-Token``
    and returns transport's outcome unchanged. Radar holds no backend credential
    and sends none: the request has no body, and transport refreshes only the
    credential stored for the crew's own backend and profile.

    Any failure to get an outcome, including transport answering with a non-200
    status such as 404 for an unknown crew, becomes a 502 with a fixed message.
    """
    if not _is_same_origin(request):
        return JSONResponse({"error": "cross-origin request rejected"}, status_code=403)
    crew_id = request.path_params.get("crew_id", "")
    if not _CREW_ID_RE.fullmatch(crew_id):
        return JSONResponse({"error": "crew not found"}, status_code=404)
    url = f"{TRANSPORT_URL}/internal/crews/{crew_id}/auth/refresh"
    headers = {"X-Transport-Token": _TRANSPORT_SECRET}
    try:
        async with httpx.AsyncClient(timeout=_AUTH_REFRESH_TIMEOUT_SECS) as client:
            resp = await client.post(url, headers=headers)
    except httpx.RequestError as exc:
        logger.error(
            "Transport unreachable for crew auth refresh %s (%s)", crew_id, type(exc).__name__,
        )
        return JSONResponse({"error": "transport unreachable"}, status_code=502)

    if resp.status_code != 200:
        logger.error(
            "Transport returned %d for crew auth refresh %s", resp.status_code, crew_id,
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


# Radar's ES modules import each other by plain path with no version in the URL.
# Without an explicit policy, browsers cache them heuristically and can pair a new
# module with a stale one after an upgrade, which breaks the page on a missing
# export. "no-cache" makes the browser revalidate each load; the ETag keeps an
# unchanged file to a 304.
_REVALIDATE = "no-cache"


class _RevalidatingStaticFiles(StaticFiles):
    """StaticFiles that tells browsers to revalidate every response."""

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = _REVALIDATE
        return response


async def index(request: Request) -> FileResponse:
    """GET / — serve the Radar SPA root (index.html)."""
    return FileResponse(
        str(_STATIC_DIR / "index.html"),
        media_type="text/html",
        headers={"Cache-Control": _REVALIDATE},
    )


# ── Application ─────────────────────────────────────────────────────────────────

app = Starlette(
    routes=[
        Route("/health", health),
        Route("/api/crews", api_crews),
        Route("/api/crews/{crew_id}/agents", api_crew_agents),
        Route("/api/crews/{crew_id}/mail-subjects", api_crew_mail_subjects),
        Route("/api/crews/{crew_id}/auth/refresh", api_crew_auth_refresh, methods=["POST"]),
        Route("/", index),
        Mount("/static", _RevalidatingStaticFiles(directory=str(_STATIC_DIR)), name="static"),
    ],
)
