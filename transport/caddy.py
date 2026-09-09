"""transport/caddy.py — Caddy admin-API management and UI port pool (TRN-116).

Extracted from server.py to improve navigability.  This module owns:

  * The UI port pool (``_dashboard_ports_in_use`` set) and its
    allocate/release helpers.  These MUST be called while holding
    ``_registry_lock`` so allocation and the subsequent registry write are
    atomic — the lock is imported from ``registry`` (the leaf module that
    defines it; server.py and lifecycle.py import it from the same place).
  * The Caddy admin-API helpers that register / deregister a per-crew
    dashboard reverse-proxy server.

Dual-path import pattern (container flat layout vs. local dev package):
    try:
        import caddy as _caddy             # /app/caddy.py  (container)
    except ModuleNotFoundError:
        from transport import caddy as _caddy  # local dev

The container deploys all transport/*.py files flat under /app, so both
paths must remain importable.

Runtime configuration (``port``, ``api_key``) is resolved by server.py and
passed to a ``CaddyPortal`` instance's constructor (TRN-141), replacing the
former ``_caddy.PORT = ...`` / ``_caddy.GA_API_KEY = ...`` post-import mutation.
``CaddyPortal`` owns UI-port allocation and the Caddy admin-API crew
(de)registration; the module-level ``_allocate_dashboard_port`` /
``_release_dashboard_port`` / ``_caddy_register_crew`` / ``_caddy_deregister_crew``
functions remain as thin wrappers over a lazily-built module-default portal so
in-isolation use and existing tests keep working. The port-range constants are
read from ``config`` directly since they are pure cfg values. Keeping config on
the instance (rather than importing server) keeps the dependency graph acyclic:
caddy imports only stdlib, httpx, config, and registry — never server or
lifecycle.
"""

from __future__ import annotations

import logging
import time

import httpx

try:
    from config import Config  # container: flat /app/
except ImportError:
    from transport.config import Config  # local dev

try:
    from registry import _registry_lock  # noqa: F401  (re-exported for callers)
except ModuleNotFoundError:
    from transport.registry import _registry_lock  # noqa: F401


logger = logging.getLogger("transport.server")

_cfg = Config.from_env()

# ── Runtime config (see module docstring) ─────────────────────────────────────
# TRN-141: CaddyPortal (below) is the OOP owner of runtime config — server.py
# constructs one instance after it resolves PORT/GA_API_KEY and calls the
# instance methods. These module-level names remain as defaults so the module
# stays importable/testable in isolation, and the module-level functions below
# stay as thin wrappers over a lazily-built module-default CaddyPortal so
# existing call sites and tests continue to work. The port-range constants are
# pure cfg values and are read directly.
PORT: int = _cfg.port
GA_API_KEY: str = ""
GA_DASHBOARD_PORT_RANGE_START: int = _cfg.ga_dashboard_port_range_start
GA_DASHBOARD_PORT_RANGE_SIZE: int = _cfg.ga_dashboard_port_range_size


# ── UI port pool (TRN-80) ─────────────────────────────────────────────────────
# Tracks which host ports in the UI port range are currently allocated to a
# crew. Populated from crews.json at startup (see server.py __main__) and
# mutated only inside _allocate_dashboard_port / _release_dashboard_port.
# Protected by the global _registry_lock (same lock used for crews.json writes)
# so allocation and registry persistence are atomic.
_dashboard_ports_in_use: set[int] = set()


# ── CaddyPortal (TRN-141) ─────────────────────────────────────────────────────

class CaddyPortal:
    """Owns UI-port allocation and the Caddy admin-API crew (de)registration.

    Replaces the ``_caddy.PORT = ...`` / ``_caddy.GA_API_KEY = ...`` post-import
    mutation pattern with an explicit constructor: server.py builds one instance
    after it resolves the runtime config, instead of reaching into this module's
    globals. The circular-import constraint is preserved — this class is defined
    in ``caddy.py`` (which imports only stdlib/httpx/config/registry) and
    constructed in ``server.py``.

    The port pool (``_dashboard_ports_in_use``) remains a module-level set so a
    single pool is shared regardless of how many portals exist; allocation is
    still expected to happen under ``_registry_lock`` (same invariant as before).
    """

    def __init__(
        self,
        port: int,
        api_key: str,
        port_range_start: int,
        port_range_size: int,
    ) -> None:
        self._port = port
        self._api_key = api_key
        self._range_start = port_range_start
        self._range_size = port_range_size

    def allocate_port(self) -> int:
        """Scan the UI port range and allocate the first free port.

        Must be called while holding ``_registry_lock`` so the allocation and
        the subsequent registry write are atomic.

        Returns the allocated port. Raises RuntimeError if the range is full.
        """
        for port in range(self._range_start, self._range_start + self._range_size):
            if port not in _dashboard_ports_in_use:
                _dashboard_ports_in_use.add(port)
                return port
        raise RuntimeError("UI port pool exhausted")

    def release_port(self, port: int) -> None:
        """Remove ``port`` from the in-use set (no-op if not present).

        Must be called while holding ``_registry_lock`` (same invariant as
        allocate_port).
        """
        _dashboard_ports_in_use.discard(port)

    def register_crew(self, crew_id: str, port: int, crew_cookie: str = "") -> None:
        """Register a per-crew Caddy dashboard server via the admin API.

        See the module-level ``_caddy_register_crew`` docstring for the full
        behaviour. Uses this instance's ``_port`` and ``_api_key`` in place of
        the former module globals.
        """
        _transport_addr = f"ga-transport:{self._port}"

        # TRN-102: Caddy routes dashboard traffic to the transport's UI proxy,
        # which injects the session cookie. Rewrite the incoming path so it is
        # prefixed with /crews/{crew_id}/ui — {http.request.uri.path} preserves
        # the original path (and Caddy re-appends the query string
        # automatically).
        # TRN-107: every upstream request to ga-transport must carry the portal
        # secret, read from the mounted Podman secret file — same placeholder
        # install.sh uses for the static routes. Without this,
        # TransportSecretMiddleware rejects the request with 401 before it ever
        # reaches the UI-proxy or /dashboard/auth handlers.
        _transport_token_header = {
            "X-Transport-Token": ["{file./run/secrets/ga-transport-secret}"],
        }

        crew_proxy_handler: dict = {
            "handler": "reverse_proxy",
            "upstreams": [{"dial": _transport_addr}],
            "rewrite": {"uri": f"/crews/{crew_id}/ui{{http.request.uri.path}}"},
            "headers": {"request": {"set": dict(_transport_token_header)}},
        }

        # forward_auth equivalent using only standard Caddy modules (no
        # caddy-security). Only used when the API key is set — gates access with
        # a gs_session cookie check.
        forward_auth_handler = {
            "handler": "reverse_proxy",
            "upstreams": [{"dial": _transport_addr}],
            "rewrite": {"method": "GET", "uri": f"/dashboard/auth?port={port}"},
            "headers": {
                "request": {
                    "set": {
                        "X-Forwarded-Method": ["{http.request.method}"],
                        "X-Forwarded-Uri": ["{http.request.uri}"],
                        **_transport_token_header,
                    }
                },
            },
            "handle_response": [
                {
                    "match": {"status_code": [2]},
                    "routes": [
                        {"handle": [{"handler": "vars"}]},
                    ],
                }
            ],
        }

        handles = (
            [forward_auth_handler, crew_proxy_handler]
            if self._api_key
            else [crew_proxy_handler]
        )

        server_obj = {
            "@id": f"crew-{crew_id}",
            "listen": [f":{port}"],
            "routes": [
                {
                    "handle": handles,
                }
            ],
        }

        url = f"{_caddy_admin_url()}/config/apps/http/servers/crew-{crew_id}"
        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = httpx.put(url, json=server_obj, timeout=5.0)
                if resp.status_code in (200, 201):
                    logger.info(
                        "TRN-92: registered Caddy server crew-%s on port %d", crew_id, port
                    )
                    return
                # 409 Conflict means the @id already exists — idempotent success
                if resp.status_code == 409:
                    logger.info(
                        "TRN-92: Caddy server crew-%s already exists (409) — idempotent", crew_id
                    )
                    return
                logger.warning(
                    "TRN-92: Caddy register crew-%s returned %d (attempt %d/%d): %s",
                    crew_id, resp.status_code, attempt + 1, max_retries, resp.text[:200],
                )
            except Exception as exc:
                logger.warning(
                    "TRN-92: Caddy register crew-%s failed (attempt %d/%d): %s",
                    crew_id, attempt + 1, max_retries, exc,
                )
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 0s, 1s, 2s → ~3s total

    def deregister_crew(self, crew_id: str) -> None:
        """Remove a per-crew Caddy dashboard server via the admin API.

        See the module-level ``_caddy_deregister_crew`` docstring for the full
        behaviour.
        """
        url = f"{_caddy_admin_url()}/id/crew-{crew_id}"
        try:
            resp = httpx.delete(url, timeout=5.0)
            if resp.status_code in (200, 204):
                logger.info("TRN-92: deregistered Caddy server crew-%s", crew_id)
            elif resp.status_code == 404:
                logger.debug(
                    "TRN-92: Caddy server crew-%s not found on deregister (404) — OK", crew_id
                )
            else:
                logger.warning(
                    "TRN-92: Caddy deregister crew-%s returned %d: %s",
                    crew_id, resp.status_code, resp.text[:200],
                )
        except Exception as exc:
            logger.warning("TRN-92: Caddy deregister crew-%s failed: %s", crew_id, exc)


# Module-default CaddyPortal — lazily built from the module globals so the
# thin-wrapper functions below (and tests that call them directly) keep working
# without an explicit instance. server.py constructs its own instance and calls
# its methods directly; this default only backs the module-level wrappers.
_default_portal: "CaddyPortal | None" = None


def _get_default_portal() -> "CaddyPortal":
    """Return the module-default CaddyPortal, rebuilding it from the current
    module globals each call so post-import global tweaks (and tests that patch
    PORT / GA_API_KEY) are always reflected."""
    global _default_portal
    _default_portal = CaddyPortal(
        port=PORT,
        api_key=GA_API_KEY,
        port_range_start=GA_DASHBOARD_PORT_RANGE_START,
        port_range_size=GA_DASHBOARD_PORT_RANGE_SIZE,
    )
    return _default_portal


def _allocate_dashboard_port() -> int:
    """Thin wrapper over ``CaddyPortal.allocate_port`` (module-default portal).

    Must be called while holding ``_registry_lock`` so the allocation and
    the subsequent registry write are atomic. Raises RuntimeError if full.
    """
    return _get_default_portal().allocate_port()


def _release_dashboard_port(port: int) -> None:
    """Thin wrapper over ``CaddyPortal.release_port`` (module-default portal).

    Must be called while holding ``_registry_lock`` (same invariant as
    _allocate_dashboard_port).
    """
    _get_default_portal().release_port(port)


# ── Caddy admin API helpers (TRN-92) ─────────────────────────────────────────

def _caddy_admin_url() -> str:
    """Return the Caddy admin API base URL."""
    return "http://ga-portal:2019"


def _caddy_register_crew(crew_id: str, port: int, crew_cookie: str = "") -> None:
    """Thin wrapper over ``CaddyPortal.register_crew`` (module-default portal).

    Builds an HTTP server object bound to *port* with ``@id: crew-{crew_id}``.
    The crew ``reverse_proxy`` dials ``ga-transport:{PORT}`` and rewrites the
    incoming path to ``/crews/{crew_id}/ui/{original_path}`` (TRN-102). The
    transport's UI-proxy endpoint injects the ``mc_token_5476`` session cookie
    from ga-transport's own IP, satisfying the gateway's IP binding — Caddy no
    longer talks to crew gateways (``gs-*``) directly and no longer injects the
    cookie itself. When ``GA_API_KEY`` is set, a ``forward_auth`` check against
    ``/dashboard/auth`` (also on ga-transport) gates the proxy.

    Retries up to 3 times with exponential backoff (~7 s total). Logs a
    warning on failure — does not raise, so a Caddy startup race does not
    cause ``launch`` to fail.

    Must be called while holding ``_registry_lock``.

    ``crew_cookie`` is accepted for backward-compatible call sites but is no
    longer used — the transport owns cookie injection (TRN-102).
    """
    _get_default_portal().register_crew(crew_id, port, crew_cookie=crew_cookie)


def _caddy_deregister_crew(crew_id: str) -> None:
    """Thin wrapper over ``CaddyPortal.deregister_crew`` (module-default portal).

    Calls ``DELETE /config/id/crew-{crew_id}`` on the Caddy admin API.
    Handles 404 gracefully (server already removed). Logs a warning on other
    failures; does not raise so ``nuke`` is never blocked by Caddy errors.
    """
    _get_default_portal().deregister_crew(crew_id)
