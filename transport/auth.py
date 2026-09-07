"""transport/auth.py — ASGI authentication and rate-limit middleware (TRN-116).

Extracted from server.py to improve navigability.  All classes and helpers
in this module are self-contained: they import only from stdlib, security,
and each other.  They do NOT import from lifecycle or server.

Dual-path import pattern (container flat layout vs. local dev package):
    try:
        import auth as _auth              # /app/auth.py  (container)
    except ModuleNotFoundError:
        from transport import auth as _auth   # local dev

The container deploys all transport/*.py files flat under /app, so both
paths must remain importable.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import threading
from typing import Any

try:
    import security as _security          # container: flat in /app
except ModuleNotFoundError:
    from transport import security as _security  # local dev


# TRN-116: this middleware was extracted from server.py. Its log records are
# part of the transport's observable behaviour (operators grep the
# "transport.server" logger, and tests assert on it), so we deliberately keep
# the original logger name rather than switching to __name__ ("transport.auth").
logger = logging.getLogger("transport.server")


# ── Bearer token parse helper ─────────────────────────────────────────────────

def _parse_bearer_token(header_value: str) -> str | None:
    """Extract the token from an ``Authorization: Bearer <token>`` header value.

    Returns the token string if the header is well-formed (case-insensitive
    ``Bearer`` scheme, exactly one space, no embedded spaces in the token).
    Returns ``None`` on any malformed or missing input.
    """
    if not header_value:
        return None
    if len(header_value) < 8:
        return None
    if header_value[:7].lower() != "bearer ":
        return None
    token = header_value[7:].strip()
    if not token or " " in token:
        return None
    return token


# ── Rate-limit configuration (TRN-52) ─────────────────────────────────────────
# Per-endpoint sliding-window limits, each overridable via a GA_RATE_LIMIT_*
# env var in "<count>:<window_secs>" format. GA_RATE_LIMIT_ENABLED is the master
# switch (default "true"); state is in-memory and resets on process restart.
# Defaults, keyed by the endpoint name RateLimitMiddleware matches on:
_RATE_LIMIT_DEFAULTS: dict[str, tuple[str, int, int]] = {
    # endpoint_key: (env_var_name, default_count, default_window_secs)
    "login_get": ("GA_RATE_LIMIT_LOGIN_GET", 30, 60),
    "login_post": ("GA_RATE_LIMIT_LOGIN_POST", 5, 300),
    "mcp": ("GA_RATE_LIMIT_MCP", 300, 60),
    "files": ("GA_RATE_LIMIT_FILES", 60, 60),
    "crew_api": ("GA_RATE_LIMIT_CREW_API", 120, 60),
    # TRN-92: dashboard login endpoint rate limit (default 60 req / 60 s).
    # /dashboard/auth (forward_auth) is called by Caddy per-request; keep it
    # generous. /dashboard/login (the key check) is more sensitive.
    "dashboard_auth": ("GA_RATE_LIMIT_DASHBOARD_AUTH", 600, 60),
}


def _request_source(scope_or_request: Any) -> str | None:
    """Best-effort client source (IP) for audit events; None if unavailable.

    Accepts either an ASGI scope dict or a Starlette Request object.
    """
    # ASGI scope dict
    if isinstance(scope_or_request, dict):
        for k, v in scope_or_request.get("headers", []):
            if k == b"x-forwarded-for":
                return v.decode("latin-1").split(",")[0].strip()
        client = scope_or_request.get("client")
        if client:
            return client[0] if isinstance(client, (tuple, list)) else None
        return None
    # Starlette Request object
    try:
        client = getattr(scope_or_request, "client", None)
        if client is not None:
            return (
                getattr(client, "host", None)
                or (client[0] if isinstance(client, (tuple, list)) else None)
            )
    except Exception:
        pass
    return None


def _parse_rate_limit_var(
    name: str, default_count: int, default_window: int
) -> tuple[int, int]:
    """Parse a GA_RATE_LIMIT_* env var of the form "<count>:<window_secs>".

    Both fields must be positive integers. On any parse failure the default
    (count, window) is returned and a WARNING naming the variable is logged.
    """
    raw = os.environ.get(name)
    if not raw:
        return default_count, default_window
    try:
        count_str, window_str = raw.split(":", 1)
        count = int(count_str)
        window = int(window_str)
        if count <= 0 or window <= 0:
            raise ValueError("count and window must be positive integers")
        return count, window
    except (ValueError, AttributeError) as e:
        logger.warning(
            "Could not parse %s=%r (expected \"<count>:<window_secs>\", positive "
            "integers): %s. Using default %d:%d.",
            name, raw, e, default_count, default_window,
        )
        return default_count, default_window


def _build_rate_limiters() -> "dict[str, _security.RateLimiter] | None":
    """Build the per-endpoint RateLimiter map from GA_RATE_LIMIT_* env vars.

    Returns None when GA_RATE_LIMIT_ENABLED is "false" (master switch), so the
    caller can skip wrapping RateLimitMiddleware entirely.
    """
    enabled = os.environ.get("GA_RATE_LIMIT_ENABLED", "true").strip().lower()
    if enabled == "false":
        return None
    limiters: dict[str, _security.RateLimiter] = {}
    for endpoint_key, (env_var, dc, dw) in _RATE_LIMIT_DEFAULTS.items():
        count, window = _parse_rate_limit_var(env_var, dc, dw)
        limiters[endpoint_key] = _security.RateLimiter(
            max_requests=count, window_secs=float(window)
        )
    return limiters


# ── TransportSecretMiddleware ──────────────────────────────────────────────────

class TransportSecretMiddleware:
    """ASGI middleware enforcing the GA_TRANSPORT_SECRET X-Transport-Token gate (TRN-107).

    When ``transport_secret`` is non-empty, every incoming HTTP request must carry
    an ``X-Transport-Token`` header whose value matches ``transport_secret`` exactly
    (constant-time comparison). Requests missing the header or presenting a
    wrong value receive HTTP 401 immediately, before any other middleware.

    This middleware is the outermost gate — it runs before ``BearerAuthMiddleware``
    and ``SecurityHeadersMiddleware``. Crew containers on ``ga-starboard`` can dial
    ``ga-transport``, but they never receive ``GA_TRANSPORT_SECRET`` and therefore
    cannot forge the header.

    When ``transport_secret`` is empty (e.g. dev/test environment without the
    Podman secret) the middleware is a transparent pass-through.

    Non-HTTP ASGI scopes (WebSocket, lifespan) pass through unchanged.
    """

    def __init__(self, app, transport_secret: str = "") -> None:
        self.app = app
        self._secret = transport_secret

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or not self._secret:
            await self.app(scope, receive, send)
            return

        # Extract X-Transport-Token from request headers.
        headers = dict(scope.get("headers", []))
        token = headers.get(b"x-transport-token", b"").decode("latin-1")

        if not hmac.compare_digest(token, self._secret):
            from starlette.responses import Response
            response = Response(
                content="Unauthorized",
                status_code=401,
                headers={"WWW-Authenticate": "Transport-Token"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


# ── RateLimitMiddleware ────────────────────────────────────────────────────────

class RateLimitMiddleware:
    """ASGI middleware enforcing per-endpoint sliding-window rate limits.

    Applied outside ``BearerAuthMiddleware`` so all callers are subject to
    limits, including unauthenticated ``/login`` requests. ``/health`` and
    ``/version`` are unconditionally exempt and never return 429. Non-HTTP ASGI
    scopes (WebSocket, lifespan) pass through unchanged. Paths not covered by
    any registered limiter pass through without a rate check.

    Caller identity is a composite key: the source IP alone when no bearer
    token is presented, or ``SHA-256(token)[:8]:<ip>`` when one is — the raw
    token value is never stored in limiter state.
    """

    _EXEMPT: frozenset[str] = frozenset({"/health", "/version"})

    def __init__(self, app, limiters: "dict[str, _security.RateLimiter]", api_key: str = "") -> None:
        self.app = app
        self._limiters = limiters
        self._api_key = api_key

    def _caller_key(self, scope: dict, bearer_token: str | None) -> str:
        # Source IP: X-Forwarded-For first hop, else ASGI client.
        source_ip = None
        for k, v in scope.get("headers", []):
            if k == b"x-forwarded-for":
                source_ip = v.decode("latin-1").split(",")[0].strip()
                break
        if source_ip is None:
            client = scope.get("client")
            source_ip = client[0] if client else "unknown"

        if not bearer_token:
            return source_ip
        # Hash the token so its raw value is never held in limiter state.
        key_prefix = hashlib.sha256(bearer_token.encode()).hexdigest()[:8]
        return f"{key_prefix}:{source_ip}"

    @staticmethod
    def _match_endpoint(method: str, path: str) -> str | None:
        """Return the limiter key for a request, or None if unmatched.

        Priority order: login_post, login_get, files, crew_api, mcp.
        """
        if method == "POST" and path == "/login":
            return "login_post"
        if method == "GET" and path == "/login":
            return "login_get"
        if path.startswith("/files/"):
            return "files"
        # /crews/<id>/api and /crews/<id>/api/<sub>
        parts = path.lstrip("/").split("/")
        if len(parts) >= 3 and parts[0] == "crews" and parts[2] == "api":
            return "crew_api"
        # TRN-92: dashboard auth/login endpoints
        if path in ("/dashboard/login", "/dashboard/auth"):
            return "dashboard_auth"
        if path.startswith("/mcp"):
            return "mcp"
        return None

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path in self._EXEMPT:
            await self.app(scope, receive, send)
            return
        method = scope.get("method", "")
        endpoint_key = self._match_endpoint(method, path)
        limiter = self._limiters.get(endpoint_key) if endpoint_key else None
        if limiter is None:
            await self.app(scope, receive, send)
            return

        # Extract bearer token (best-effort — may be absent or invalid).
        bearer: str | None = None
        for k, v in scope.get("headers", []):
            if k == b"authorization":
                bearer = _parse_bearer_token(v.decode("latin-1"))
                break
        caller = self._caller_key(scope, bearer)

        if not limiter.record(caller):
            retry_after = str(int(limiter.window_secs)).encode("latin-1")
            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    [b"content-type", b"text/plain; charset=utf-8"],
                    [b"retry-after", retry_after],
                ],
            })
            await send({
                "type": "http.response.body",
                "body": b"Rate limit exceeded. Retry after " + retry_after + b" seconds.",
            })
            return

        await self.app(scope, receive, send)


# ── BearerAuthMiddleware ───────────────────────────────────────────────────────

class BearerAuthMiddleware:
    """Pure ASGI middleware enforcing a static bearer API key.

    When ``api_key`` is empty the middleware is a transparent pass-through.
    Otherwise every HTTP request must carry exactly one ``Authorization: Bearer <key>``
    header matching the configured value (constant-time comparison). Rejected
    requests receive 401 with ``WWW-Authenticate: Bearer`` and never reach the
    downstream app. Non-HTTP ASGI scopes pass through unchanged.

    Login/logout routes are also handled here so the inner app (mcp_app) is
    never wrapped in a Starlette router — that would break the MCP lifespan.

    ``routes`` and ``public_routes`` are injected by server.py at construction
    time to avoid importing server.py from this module (which would create a
    cycle).  Each is a ``{(method, path): handler}`` mapping.  Handlers are
    async callables ``(Request) -> Response``.
    """

    def __init__(
        self,
        app,
        api_key: str = "",
        file_app=None,
        routes: "dict[tuple[str, str], Any] | None" = None,
        public_routes: "dict[tuple[str, str], Any] | None" = None,
    ) -> None:
        self.app = app
        self._key = api_key
        self._file_app = file_app
        self._routes: dict[tuple[str, str], Any] = routes if routes is not None else {}
        self._public_routes: dict[tuple[str, str], Any] = public_routes if public_routes is not None else {}

    # Paths that bypass API-key auth (readiness probes, etc.)
    _PUBLIC_PATHS: set[str] = {"/health"}

    async def __call__(self, scope, receive, send) -> None:
        from starlette.requests import Request

        # TRN-102: WebSocket upgrades for /crews/<id>/ui/<path> are proxied to
        # the crew gateway with the session cookie injected. Access is gated by
        # Caddy's forward_auth upstream (keyed deployments); the transport's
        # bearer check applies to HTTP scopes only, so WS is dispatched here.
        if scope["type"] == "websocket":
            _ws_parts = scope.get("path", "").lstrip("/").split("/")
            if (
                len(_ws_parts) >= 3
                and _ws_parts[0] == "crews"
                and _ws_parts[2] == "ui"
            ):
                # Delegate to the registered ws_proxy handler if present.
                ws_handler = self._routes.get(("WS", "/crews/*/ui"))
                if ws_handler is not None:
                    await ws_handler(scope, receive, send)
                    return
            await self.app(scope, receive, send)
            return

        # Public routes — served without any authentication check
        if scope["type"] == "http":
            public_handler = self._public_routes.get(
                (scope["method"], scope["path"])
            )
            if public_handler is not None:
                request = Request(scope, receive)
                response = await public_handler(request)
                await response(scope, receive, send)
                return

            # File routes — use presigned-URL auth, bypass API key
            if self._file_app and scope["path"].startswith("/files/"):
                await self._file_app(scope, receive, send)
                return

        if not self._key or scope["type"] != "http":
            # No API key — still need to check login/logout routes
            if scope["type"] == "http":
                handler = self._routes.get(
                    (scope["method"], scope["path"])
                )
                if handler is not None:
                    request = Request(scope, receive)
                    response = await handler(request)
                    await response(scope, receive, send)
                    return
                # TRN-80: per-port UI proxy — requests arriving on a crew UI
                # port are proxied to that crew's gateway. Auth is skipped here
                # only when GA_API_KEY is unset; the keyed path checks auth first.
                # TRN-101: Per-port proxy removed; Portal (ga-portal) owns all
                # dashboard port bindings. This block is intentionally gone.
                # Crew proxy routes (no auth required when GA_API_KEY unset)
                _path = scope["path"]
                _parts = _path.lstrip("/").split("/")
                if len(_parts) >= 3 and _parts[0] == "crews" and _parts[2] == "ui":
                    ui_proxy = self._routes.get(("GET", "/crews/*/ui"))
                    if ui_proxy is not None:
                        request = Request(scope, receive)
                        response = await ui_proxy(request)
                        await response(scope, receive, send)
                        return
                if len(_parts) >= 4 and _parts[0] == "crews" and _parts[2] == "api":
                    api_proxy = self._routes.get(("GET", "/crews/*/api"))
                    if api_proxy is not None:
                        request = Request(scope, receive)
                        response = await api_proxy(request)
                        await response(scope, receive, send)
                        return
                # TRN-80: POST/DELETE /crews/{id}/dashboard
                if (
                    len(_parts) == 3
                    and _parts[0] == "crews"
                    and _parts[2] == "dashboard"
                ):
                    request = Request(scope, receive)
                    if scope["method"] == "POST":
                        dash_post = self._routes.get(("POST", "/crews/*/dashboard"))
                        if dash_post is not None:
                            response = await dash_post(request)
                            await response(scope, receive, send)
                            return
                    elif scope["method"] == "DELETE":
                        dash_delete = self._routes.get(("DELETE", "/crews/*/dashboard"))
                        if dash_delete is not None:
                            response = await dash_delete(request)
                            await response(scope, receive, send)
                            return
                    else:
                        from starlette.responses import PlainTextResponse
                        response = PlainTextResponse("Method Not Allowed", status_code=405)
                        await response(scope, receive, send)
                        return
            await self.app(scope, receive, send)
            return

        # Allow public paths through without auth (health probes, etc.)
        if scope["path"] in self._PUBLIC_PATHS:
            handler = self._routes.get((scope["method"], scope["path"]))
            if handler is not None:
                request = Request(scope, receive)
                response = await handler(request)
                await response(scope, receive, send)
                return

        # Extract Authorization headers from the ASGI scope
        auth_values = [
            v.decode("latin-1")
            for k, v in scope.get("headers", [])
            if k == b"authorization"
        ]

        # Reject: missing, duplicated, or malformed
        if len(auth_values) != 1:
            await self._reject(send, scope)
            return

        value = auth_values[0]
        # Must be "Bearer <token>" (case-insensitive scheme)
        token = _parse_bearer_token(value)
        if token is None:
            await self._reject(send, scope)
            return

        if not token or not hmac.compare_digest(token, self._key):
            await self._reject(send, scope)
            return

        # Auth passed — check login/logout routes before falling through to MCP
        handler = self._routes.get((scope["method"], scope["path"]))
        if handler is not None:
            request = Request(scope, receive)
            response = await handler(request)
            await response(scope, receive, send)
            return

        # TRN-80: per-port UI proxy (auth enforced above)
        # TRN-101: Per-port proxy removed; Portal (ga-portal) owns all
        # dashboard port bindings. This block is intentionally gone.

        # Crew UI proxy — /crews/<id>/ui and /crews/<id>/ui/<path>
        # Dispatch after auth passes so GA_API_KEY enforcement applies.
        path = scope["path"]
        path_parts = path.lstrip("/").split("/")
        if (
            len(path_parts) >= 3
            and path_parts[0] == "crews"
            and path_parts[2] == "ui"
        ):
            ui_proxy = self._routes.get(("GET", "/crews/*/ui"))
            if ui_proxy is not None:
                request = Request(scope, receive)
                response = await ui_proxy(request)
                await response(scope, receive, send)
                return

        # Crew API proxy — /crews/<id>/api/<path>
        if (
            len(path_parts) >= 4
            and path_parts[0] == "crews"
            and path_parts[2] == "api"
        ):
            api_proxy = self._routes.get(("GET", "/crews/*/api"))
            if api_proxy is not None:
                request = Request(scope, receive)
                response = await api_proxy(request)
                await response(scope, receive, send)
                return

        # TRN-80: POST/DELETE /crews/{id}/dashboard (keyed path — auth already passed above)
        if (
            len(path_parts) == 3
            and path_parts[0] == "crews"
            and path_parts[2] == "dashboard"
        ):
            from starlette.responses import PlainTextResponse
            request = Request(scope, receive)
            if scope["method"] == "POST":
                dash_post = self._routes.get(("POST", "/crews/*/dashboard"))
                if dash_post is not None:
                    response = await dash_post(request)
                    await response(scope, receive, send)
                    return
            elif scope["method"] == "DELETE":
                dash_delete = self._routes.get(("DELETE", "/crews/*/dashboard"))
                if dash_delete is not None:
                    response = await dash_delete(request)
                    await response(scope, receive, send)
                    return
            else:
                response = PlainTextResponse("Method Not Allowed", status_code=405)
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(send, scope=None) -> None:
        # Audit the authorization denial (TRN-70 audit logging). No token value
        # is ever included — only outcome, source, and timestamp.
        try:
            source = None
            if scope is not None:
                for k, v in scope.get("headers", []):
                    if k == b"x-forwarded-for":
                        source = v.decode("latin-1").split(",")[0].strip()
                        break
                if source is None:
                    client = scope.get("client")
                    if client:
                        source = client[0]
            _security.audit_auth_event(
                action="api_request", outcome="denied", account=None,
                source=source, emit=logger.info,
            )
        except Exception:
            pass
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                [b"www-authenticate", b"Bearer"],
                [b"content-type", b"text/plain; charset=utf-8"],
            ],
        })
        await send({
            "type": "http.response.body",
            "body": b"Unauthorized",
        })


# ── SecurityHeadersMiddleware ──────────────────────────────────────────────────

class SecurityHeadersMiddleware:
    """ASGI middleware enforcing transport-security guarantees.

    - Redirects plaintext HTTP to HTTPS with a 301 when the redirect is enabled
      (staged rollout: off until the monitored plaintext window + client notice
      is complete).
    - Emits the baseline security headers on every response
      (``X-Content-Type-Options: nosniff``, clickjacking protection, and a
      Content-Security-Policy) and, on HTTPS responses, an HSTS header with a
      non-zero max-age.

    HTTPS is detected from the ASGI scheme or the ``x-forwarded-proto`` header,
    since TLS is terminated at the edge and the app sees forwarded requests.
    """

    def __init__(
        self,
        app,
        *,
        enable_headers: bool = True,
        enforce_redirect: bool = False,
        csp_enforce: bool = False,
    ) -> None:
        self.app = app
        self._enable_headers = enable_headers
        self._enforce_redirect = enforce_redirect
        self._csp_enforce = csp_enforce

    @staticmethod
    def _is_https(scope) -> bool:
        if scope.get("scheme") == "https":
            return True
        for k, v in scope.get("headers", []):
            if k == b"x-forwarded-proto" and v.split(b",")[0].strip().lower() == b"https":
                return True
        return False

    @staticmethod
    def _host(scope) -> str:
        for k, v in scope.get("headers", []):
            if k == b"host":
                return v.decode("latin-1")
        server = scope.get("server") or ("localhost", None)
        return server[0]

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        https = self._is_https(scope)

        # Log plaintext HTTP traffic (TRN-70 task 3.4).
        # HTTPS redirect is disabled (Caddy owns redirects); log plaintext hits
        # for visibility.
        if not https and scope.get("path") != "/health":
            source = None
            for k, v in scope.get("headers", []):
                if k == b"x-forwarded-for":
                    source = v.decode("latin-1").split(",")[0].strip()
                    break
            if source is None:
                client = scope.get("client")
                if client:
                    source = client[0]
            logger.info(
                "plaintext HTTP hit: method=%s path=%s source=%s",
                scope.get("method", "?"),
                scope.get("path", "/"),
                source or "-",
            )

        # Plaintext → HTTPS 301 redirect (staged; skip health probes).
        if self._enforce_redirect and not https and scope.get("path") != "/health":
            host = self._host(scope)
            path = scope.get("path", "/")
            qs = scope.get("query_string", b"")
            target = f"https://{host}{path}"
            if qs:
                # Strip control characters to prevent CRLF injection in Location.
                sanitised = re.sub(r"[\x00-\x1f\x7f]", "", qs.decode("latin-1"))
                target += "?" + sanitised
            await send({
                "type": "http.response.start",
                "status": 301,
                "headers": [
                    (b"location", target.encode("latin-1")),
                    (b"content-length", b"0"),
                ],
            })
            await send({"type": "http.response.body", "body": b""})
            return

        if not self._enable_headers:
            await self.app(scope, receive, send)
            return

        extra = _security.security_headers(
            https=https,
            csp_report_only=not self._csp_enforce,
        )

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {k.lower() for k, _ in headers}
                for name, value in extra:
                    if name not in present:
                        headers.append((name, value))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)
