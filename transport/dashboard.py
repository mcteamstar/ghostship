"""transport/dashboard.py — dashboard auth/session gate (TRN-141).

``DashboardGate`` encapsulates the dashboard state cluster that previously
lived as five module-level globals in ``server.py``
(``_dashboard_throttle``, ``_gs_sessions``, ``_dashboard_csrf_token``,
``_dashboard_port_crew``, ``_dashboard_port_crew_lock``) together with the four
HTTP handlers that operate on it. Collecting them into one stateful object
makes the previously-implicit dependencies (session TTL, API key, TLS mode)
explicit constructor arguments.

This module imports ``security`` (for ``Throttle`` and ``SessionStore``). It
deliberately lives here rather than in ``caddy.py`` — ``caddy.py``'s documented
acyclic import constraint is stdlib/httpx/config/registry only, never
``security`` — so ``caddy.py`` stays limited to port allocation and the Caddy
admin API.

Dual-path import pattern (container flat layout vs. local dev package):
    try:
        import dashboard as _dashboard        # /app/dashboard.py (container)
    except ModuleNotFoundError:
        from transport import dashboard as _dashboard   # local dev
"""

from __future__ import annotations

import hmac
import logging
import secrets
import threading

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

try:
    import security as _security          # container: flat in /app
except ModuleNotFoundError:
    from transport import security as _security  # local dev

try:
    from auth import _request_source      # container: flat in /app
except ModuleNotFoundError:
    from transport.auth import _request_source  # local dev


# Keep the original logger name — operators grep "transport.server" and tests
# assert on it (same rationale as auth.py, TRN-116).
logger = logging.getLogger("transport.server")


# SEC-09 — open redirect guard for /dashboard/login ?next=
def _validate_next_url(url: str) -> str:
    """Validate next_url is a safe same-origin relative path.

    Returns a sanitised path, falling back to "/" for any value that could
    enable an open redirect (protocol-relative URLs, javascript: URIs, or
    anything that is not a relative path).
    """
    if not url:
        return "/"
    # Must be a relative path starting with / but not // (protocol-relative).
    # The leading-slash guard already blocks javascript: and //evil.com inputs.
    if not url.startswith("/") or url.startswith("//"):
        return "/"
    return url


class DashboardGate:
    """Encapsulates dashboard auth/session state and its HTTP handlers (TRN-141).

    Owns:
      - ``_throttle``    — brute-force protection for /dashboard/login.
      - ``_sessions``    — bounded, revocable gs_session store.
      - ``_csrf_token``  — process-lifetime CSRF token embedded in the login form.
      - ``_port_crew``   — dashboard-port → crew_id map for forward_auth lookups.
      - ``_port_crew_lock`` — guards read-modify-write of ``_port_crew``.

    Constructor dependencies (previously implicit module globals):
      - ``session_ttl_secs`` — gs_session lifetime (``cfg.ga_portal_session_ttl_secs``).
      - ``api_key``          — ``GA_API_KEY``; empty means open-access dashboard.
      - ``tls_mode``         — ``cfg.ga_portal_tls_mode``; "off" ⇒ no Secure cookie flag.
    """

    def __init__(self, session_ttl_secs: float, api_key: str, tls_mode: str) -> None:
        # Dashboard login is guarded by security.Throttle (brute-force
        # protection) and gs_session cookies are backed by
        # security.SessionStore (bounded, revocable). Both carry their own
        # internal lock and hold state in memory — lost on transport restart
        # (acceptable — users re-login; an active attacker only regains the
        # throttle window).
        self._throttle = _security.Throttle(max_failures=5, window_secs=900)
        self._sessions = _security.SessionStore(lifetime_secs=session_ttl_secs)
        # TRN-122: single random token generated at construction and held for
        # the process lifetime. Embedded in the GET /dashboard/login form and
        # validated on every POST before the API-key check (design.md D1).
        self._csrf_token: str = secrets.token_hex(32)
        self._api_key = api_key
        self._tls_mode = tls_mode
        # TRN-101: the per-port uvicorn proxy pool was removed. Portal
        # (ga-portal) is the sole dashboard proxy. Port→crew mapping is
        # retained for forward_auth lookups by handle_auth.
        self._port_crew: dict[int, str] = {}  # port → crew_id
        # TRN-123: guards all read-modify-write access to _port_crew, a mix of
        # asyncio and startup contexts.
        self._port_crew_lock = threading.Lock()

    # ── Port registry (TRN-92 / TRN-101) ─────────────────────────────────────

    def register_port(self, crew_id: str, port: int) -> None:
        """Record the dashboard-port → crew_id mapping for forward_auth lookups."""
        with self._port_crew_lock:
            self._port_crew[int(port)] = crew_id

    def release_port(self, port: int) -> None:
        """Remove a dashboard-port mapping (no-op if absent)."""
        with self._port_crew_lock:
            self._port_crew.pop(int(port), None)

    # ── Dashboard auth HTTP handlers (TRN-92) ─────────────────────────────────

    async def handle_login_post(self, request: Request) -> Response:
        """POST /dashboard/login — validate ga_api_key, issue gs_session cookie.

        Reads ``ga_api_key`` from the form body, constant-time compares against
        the configured API key. On success returns 200 + ``Set-Cookie:
        gs_session=...``. On failure returns 401 with no cookie.
        """
        if not self._api_key:
            # No API key configured — dashboard login is only meaningful with one.
            return Response(status_code=401)

        source = _request_source(request)
        # TRN-138: the login throttle key must come from the actual ASGI
        # connection IP (request.client.host), NOT X-Forwarded-For, which a
        # client can spoof to evade or poison the brute-force lock (design D3).
        # _request_source() prefers XFF and is retained only for audit context.
        client = getattr(request, "client", None)
        throttle_source = getattr(client, "host", None) if client is not None else None
        # Throttle brute-force attempts before touching the credential (avoids a
        # timing oracle on the reject path — see design D3).
        if self._throttle.is_locked(account="dashboard", source=throttle_source):
            return Response(status_code=429)

        try:
            form = await request.form()
            provided = str(form.get("ga_api_key", ""))
            # TRN-122: read and validate CSRF token before touching the API-key
            # path. Fail-fast on forged submissions (design.md D4).
            provided_csrf = str(form.get("csrf_token", ""))
            # TRN-138: capture the submitted next URL so the server — not the
            # client — is the source of truth for the post-login redirect target.
            next_url = _validate_next_url(str(form.get("next", "/")))
        except Exception:
            return Response(status_code=400)

        if not hmac.compare_digest(provided_csrf, self._csrf_token):
            return Response(status_code=403)

        if not hmac.compare_digest(provided, self._api_key):
            self._throttle.record_failure(account="dashboard", source=throttle_source)
            return Response(status_code=401)

        self._throttle.record_success(account="dashboard", source=throttle_source)

        token = self._sessions.issue()
        # Build Set-Cookie header manually — avoids starlette version
        # differences and is more explicit about the exact cookie attributes.
        # The Secure flag is only set when the portal runs behind TLS
        # (TRN-121); a plain-HTTP portal must not set Secure or the browser
        # drops the cookie.
        secure_attr = "; Secure" if self._tls_mode != "off" else ""
        cookie_value = (
            f"gs_session={token}; HttpOnly; SameSite=Lax{secure_attr}; Path=/"
        )
        # TRN-138: return the server-sanitised next URL in the JSON body so the
        # login-form JS redirects from _validate_next_url() output rather than
        # from the raw submitted FormData field (open-redirect fix).
        return JSONResponse(
            {"ok": True, "next": next_url},
            status_code=200,
            headers={"Set-Cookie": cookie_value},
        )

    async def handle_auth(self, request: Request) -> Response:
        """GET /dashboard/auth — Caddy forward_auth endpoint.

        Validates the ``gs_session`` cookie. On 200 returns
        ``X-Crew-Cookie: mc_token_5476=<crew_cookie>`` so Caddy's
        ``copy_headers`` injects it into the upstream request to the crew
        gateway. The target crew is identified from the incoming dashboard port
        via ``_port_crew``. Returns 401 on missing/invalid session.

        When the API key is not configured, the dashboard is open-access and
        all requests are passed through immediately (200) without a session
        check.
        """
        # Open-access mode: no API key means no session gate.
        if not self._api_key:
            return Response(status_code=200)

        # Extract gs_session cookie
        token = request.cookies.get("gs_session", "")
        if not token or not self._sessions.validate(token):
            return Response(status_code=401)

        # Determine which crew this request is for by looking up the incoming
        # port. In Caddy mode the forward_auth call comes from ga-portal →
        # ga-transport, so we read the X-Forwarded-For / X-Real-Port Caddy
        # passes, or fall back to reading the original dashboard-port from a
        # custom header that the Caddy server config can inject.
        # The simplest Caddy-compatible approach: encode the crew's port in the
        # forward_auth URI, e.g. /dashboard/auth?port=64058. Caddy's
        # forward_auth directive supports arbitrary URIs. We derive the crew
        # from the port.
        port_str = request.query_params.get("port", "")
        crew_id: str | None = None
        if port_str:
            try:
                port_int = int(port_str)
                with self._port_crew_lock:
                    crew_id = self._port_crew.get(port_int)
            except ValueError:
                pass

        if crew_id is None:
            # Fallback: check X-Forwarded-Port or X-Dashboard-Port header
            fwd_port = request.headers.get("x-dashboard-port", "")
            if fwd_port:
                try:
                    with self._port_crew_lock:
                        crew_id = self._port_crew.get(int(fwd_port))
                except ValueError:
                    pass

        if crew_id is None:
            # Last resort: return 200 (session is valid; crew cookie is injected
            # directly by Caddy's crew proxy config, not here).
            return Response(status_code=200)

        # Valid session — return 200 to allow Caddy to proxy to the crew
        # gateway. The mc_token_5476 cookie is injected by the Caddy crew proxy
        # config.
        return Response(status_code=200)

    async def handle_logout_post(self, request: Request) -> Response:
        """POST /dashboard/logout — revoke the gs_session and clear the cookie.

        Validates the current ``gs_session`` cookie; returns 401 when it is
        missing/invalid. On a valid token, revokes it in the session store and
        responds with a ``Set-Cookie`` header that clears the cookie in the
        browser (TRN-121).
        """
        # TRN-138: logout is a state-changing POST — validate the CSRF token
        # before any session check, matching the login POST pattern. Reject a
        # missing or mismatched token with 403.
        try:
            form = await request.form()
            provided_csrf = str(form.get("csrf_token", ""))
        except Exception:
            return Response(status_code=400)

        if not hmac.compare_digest(provided_csrf, self._csrf_token):
            return Response(status_code=403)

        token = request.cookies.get("gs_session", "")
        if not self._sessions.validate(token):
            return Response(status_code=401)

        self._sessions.revoke(token)
        return Response(
            status_code=200,
            content="OK",
            headers={
                "Set-Cookie": (
                    "gs_session=; Max-Age=0; "
                    "Expires=Thu, 01 Jan 1970 00:00:00 GMT; "
                    "HttpOnly; SameSite=Lax; Path=/"
                )
            },
        )

    async def handle_login_get(self, request: Request) -> Response:
        """GET /dashboard/login — serve the minimal HTML login form.

        Accepts an optional ``?next=<url>`` query parameter for post-login
        redirect.
        """
        next_url = _validate_next_url(request.query_params.get("next", "/"))
        next_url_escaped = _security.encode_html_attr(next_url)
        # TRN-122: embed the CSRF token in the form so POST /dashboard/login can
        # validate it. encode_html_attr applied for defence-in-depth (hex
        # output is already safe, but the pattern matches next_url_escaped
        # usage above).
        csrf_token_escaped = _security.encode_html_attr(self._csrf_token)
        # Simple HTML login page — no external dependencies.
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ghost Academy — Login</title>
<style>
  body {{ font-family: sans-serif; display: flex; align-items: center;
         justify-content: center; min-height: 100vh; margin: 0;
         background: #0f0f0f; color: #e8e8e8; }}
  .card {{ background: #1a1a1a; border: 1px solid #333; border-radius: 8px;
           padding: 2rem; width: 320px; }}
  h1 {{ font-size: 1.2rem; margin: 0 0 1.5rem; }}
  label {{ display: block; font-size: 0.85rem; color: #aaa; margin-bottom: 0.4rem; }}
  input {{ width: 100%; box-sizing: border-box; padding: 0.6rem;
           background: #0f0f0f; border: 1px solid #444; border-radius: 4px;
           color: #e8e8e8; font-size: 1rem; }}
  button {{ margin-top: 1rem; width: 100%; padding: 0.7rem;
            background: #2d6a4f; border: none; border-radius: 4px;
            color: #fff; font-size: 1rem; cursor: pointer; }}
  button:hover {{ background: #3a8a65; }}
  .err {{ color: #e07070; font-size: 0.85rem; margin-top: 0.8rem; display: none; }}
</style>
</head>
<body>
<div class="card">
  <h1>👻 Ghost Academy</h1>
  <form id="f" method="post" action="/dashboard/login">
    <input type="hidden" name="next" value="{next_url_escaped}">
    <input type="hidden" name="csrf_token" value="{csrf_token_escaped}">
    <label for="k">API Key</label>
    <input type="password" id="k" name="ga_api_key" autocomplete="current-password" required>
    <button type="submit">Sign in</button>
    <p class="err" id="err">Invalid API key.</p>
  </form>
</div>
<script>
  const f = document.getElementById('f');
  f.addEventListener('submit', async e => {{
    e.preventDefault();
    const fd = new FormData(f);
    const r = await fetch('/dashboard/login', {{method:'POST', body: fd}});
    if (r.ok) {{
      // TRN-138: redirect to the server-sanitised next URL from the JSON
      // response body, not the raw submitted FormData field, so the open-
      // redirect guard in _validate_next_url() is always authoritative.
      let dest = '/';
      try {{ const data = await r.json(); dest = data.next || '/'; }} catch (_e) {{}}
      window.location.href = dest;
    }} else {{
      document.getElementById('err').style.display = 'block';
    }}
  }});
</script>
</body>
</html>"""
        return Response(content=html, media_type="text/html; charset=utf-8")
