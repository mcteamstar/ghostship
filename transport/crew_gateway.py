"""Crew gateway wire calls and bounded recovery.

The client owns gateway request serialization. Crew restoration may make
one-shot requests but must not recursively enter request_with_recovery.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx2 as httpx

try:
    from constants import CREW_GATEWAY_PORT
    from crew import Crew
except ModuleNotFoundError:
    from .constants import CREW_GATEWAY_PORT
    from .crew import Crew

logger = logging.getLogger(__name__)


def _crew_url(crew) -> str:
    if isinstance(crew, Crew):
        return crew.gateway_url()
    return f"http://{crew['container']}:{CREW_GATEWAY_PORT}"


def _crew_cookie(crew) -> str:
    if isinstance(crew, Crew):
        return crew.cookie_header()
    return f"mc_token_{CREW_GATEWAY_PORT}={crew['cookie']}"


# TRN-220: headers the transport host must never send to a crew gateway.
# These select the gateway's INTERNAL auth path, which KiroCrew 0.9.0
# (PR #2424 / issue #302) now peer-cred-gates over the unix socket: a caller
# whose OS UID does not match the gateway's `kirocrew` process is rejected even
# with a valid shared secret. The transport host runs under a different UID, so
# any internal-secret call from here would be rejected. The transport always
# uses the external dashboard-cookie path instead.
_FORBIDDEN_INTERNAL_HEADERS = ("X-Internal-Secret", "X-Session-Key")


class CrewUnresponsiveError(RuntimeError):
    """Raised when all recovery attempts for a crew have been exhausted."""
    pass


# Upper bound on how much of a gateway error body is echoed back to callers.
_GATEWAY_DETAIL_LIMIT = 500
_COOKIE_PATTERN = re.compile(r"mc_token_\d+=[^;\s\"']+")
_BEARER_PATTERN = re.compile(r"(?i)Authorization\s*:\s*Bearer\s+\S+")
_GS_SESSION_PATTERN = re.compile(r"gs_session=[^;\s\"']+")
_GS_CSRF_PATTERN = re.compile(r"gs_csrf=[^;\s\"']+")


def _gateway_error_detail(exc: BaseException | None, crew: dict | None) -> tuple[str, bool]:
    """Describe the gateway's final HTTP error for a give-up message.

    Returns ``(suffix, is_client_error)``. ``suffix`` is empty unless *exc* is
    an ``httpx.HTTPStatusError``; otherwise it carries the status code and the
    response body, with the crew's cookie and any ``mc_token_<port>=`` value
    redacted, whitespace collapsed and the body truncated to
    ``_GATEWAY_DETAIL_LIMIT`` characters.
    """
    if not isinstance(exc, httpx.HTTPStatusError):
        return "", False
    status = exc.response.status_code
    # best-effort: response body read can fail on incomplete/closed streams; fallback is an empty string
    try:
        body = exc.response.text or ""
    except Exception:
        body = ""
    cookie = (crew or {}).get("cookie")
    if cookie:
        body = body.replace(cookie, "[redacted]")
    body = _COOKIE_PATTERN.sub("mc_token=[redacted]", body)
    body = _BEARER_PATTERN.sub("Authorization: Bearer [redacted]", body)
    body = _GS_SESSION_PATTERN.sub("gs_session=[redacted]", body)
    body = _GS_CSRF_PATTERN.sub("gs_csrf=[redacted]", body)
    body = " ".join(body.split())[:_GATEWAY_DETAIL_LIMIT]
    return f" Last gateway response: HTTP {status}: {body}", 400 <= status < 500


def _unresponsive_error(
    crew_id: str,
    what: str,
    crew: dict | None,
    last_exc: BaseException | None,
) -> CrewUnresponsiveError:
    """Build the give-up error, carrying the gateway's last HTTP error if any.

    A 4xx means the gateway is up and refused the request, so the usual
    "check crew status" suggestion is replaced with one that points at the
    gateway's own response.
    """
    detail, client_error = _gateway_error_detail(last_exc, crew)
    if client_error:
        suggestion = "The crew gateway rejected the request; see the response above."
    else:
        suggestion = "Suggestion: check crew status with crews() or try again in a moment."
    return CrewUnresponsiveError(
        f"crew {crew_id} is unresponsive — {what}.{detail} {suggestion}"
    )


def _spawn_backend(crew: Crew | dict) -> str:
    """Select the gateway backend from the crew record, including legacy crews."""
    backend = (crew.acp_backend if isinstance(crew, Crew) else crew.get("acp_backend")) or "kiro"
    if backend not in ("kiro", "claude", "codex"):
        raise ValueError(f"Unsupported crew backend: {backend}")
    return backend


class CrewGatewayClient:
    """Shared Transport client for crew gateway operations."""

    def __init__(
        self,
        http: httpx.Client,
        *,
        refresh_cookie: Callable[[Crew | dict, str], bool],
        restore_crew: Callable[[Crew | dict, str], Crew | dict | object],
        removed_crew: object,
    ) -> None:
        self._http = http
        self._refresh_cookie = refresh_cookie
        self._restore_crew = restore_crew
        self._removed_crew = removed_crew
        self._recovery_locks: dict[str, threading.Lock] = {}
        self._recovery_locks_lock = threading.Lock()

    def recovery_lock(self, crew_id: str) -> threading.Lock:
        with self._recovery_locks_lock:
            return self._recovery_locks.setdefault(crew_id, threading.Lock())

    def forget_crew(self, crew_id: str) -> None:
        with self._recovery_locks_lock:
            self._recovery_locks.pop(crew_id, None)

    def request(self, crew: dict, method: str, path: str, **kw: Any) -> Any:
        url = _crew_url(crew)
        # TRN-220: authenticate on the external cookie path (Cookie + Origin) only.
        # Never attach the internal-secret headers — see _FORBIDDEN_INTERNAL_HEADERS.
        headers = {"Cookie": _crew_cookie(crew), "Origin": url}
        caller_headers = kw.pop("headers", None)
        if caller_headers:
            for h in _FORBIDDEN_INTERNAL_HEADERS:
                if h in caller_headers:
                    raise ValueError(
                        f"TRN-220: {h} must not be sent on the transport cookie path"
                    )
            headers.update(caller_headers)
        r = self._http.request(
            method, f"{url}{path}",
            headers=headers,
            **kw,
        )
        r.raise_for_status()
        return r.json()

    def probe(self, crew_url: str) -> bool:
        """Perform a lightweight liveness probe against the gateway root.

        GET {crew_url}/ with a 5-second timeout. Returns True on any 2xx
        response, False on non-2xx, connection refused, timeout, or any error.
        """
        try:
            r = self._http.get(f"{crew_url}/", timeout=5.0)
            return 200 <= r.status_code < 300
        except (httpx.ConnectError, httpx.ConnectTimeout, ConnectionError, OSError):
            return False

    def _phase0_transient_503(
        self,
        crew: dict,
        method: str,
        path: str,
        **kw: Any,
    ) -> Any:
        """Phase 0: task still spawning — short bounded retry on 503.

        On 503 from a per-task /api/spawn/* route, KiroCrew's own task record
        already reports elapsed > 0 before the agent process has finished
        forking/registering enough to serve the route.  Short bounded retry —
        this is transient and self-resolving within a couple of seconds.

        Re-raises the last 503 error if all retries are exhausted.
        Raises any non-503 HTTPStatusError immediately without retrying.

        Note (D6): a 503 here means the task process is still starting and has not
        served the route yet — the request was not acted upon, so retrying is safe
        for any method (including POST). The idempotency guard D6 adds is for a
        connection reset (_phase2_dead_gateway), not this transient-503 path.
        """
        last_exc: Exception | None = None
        for _attempt in range(4):
            time.sleep(1.0)
            try:
                return self.request(crew, method, path, **kw)
            except httpx.HTTPStatusError as retry_exc:
                if retry_exc.response.status_code != 503:
                    raise
                last_exc = retry_exc
        raise last_exc

    def _phase1_stale_cookie(
        self,
        crew: dict,
        crew_id: str,
        method: str,
        path: str,
        *,
        trigger_exc: BaseException | None = None,
        **kw: Any,
    ) -> Any:
        """Phase 1: stale cookie — attempt cookie refresh then retry once.

        On 400/401/403 from a running container, refreshes the session cookie
        and retries the request.  If the refresh fails or the retry fails,
        escalates to Phase 2 (full gateway restart).

        Returns the API result on success.
        Raises CrewUnresponsiveError if Phase 2 restart also fails.

        Note (D6): a stale-cookie failure is a 400/401/403 — the gateway REJECTED
        the request at auth and did not act on it, so retrying after a cookie
        refresh cannot duplicate a side effect even for a POST. The idempotency
        guard that D6 adds lives in _phase2_dead_gateway (a connection reset, where
        the request MAY have been accepted before the socket dropped), not here.
        """
        logger.info(
            "Crew %s stale-cookie phase — attempting cookie refresh",
            crew_id,
        )
        last_exc: BaseException | None = trigger_exc
        if self._refresh_cookie(crew, crew_id):
            try:
                return self.request(crew, method, path, **kw)
            except Exception as _retry_exc:
                last_exc = _retry_exc
                logger.warning(
                    "Crew %s phase-1 retry failed after cookie refresh: %s — "
                    "escalating to full restart",
                    crew_id, _retry_exc,
                )

        # Phase 1 failed — escalate to full restart
        logger.info(
            "Crew %s cookie refresh failed or retry failed — "
            "escalating to full restart",
            crew_id,
        )
        try:
            crew = self._restore_crew(crew, crew_id)
        except RuntimeError:
            raise _unresponsive_error(
                crew_id,
                "transport attempted cookie refresh and container restart but "
                "the gateway did not recover",
                crew, last_exc,
            )
        # TRN-238 QA-2: crew was nuked during the restart — the registry entry is
        # gone, so there is nothing to call the API against. Surface a clear error.
        if crew is self._removed_crew:
            raise CrewUnresponsiveError(
                f"crew {crew_id} was removed (nuked) during restart — no longer exists."
            )
        try:
            return self.request(crew, method, path, **kw)
        except Exception as final_exc:
            raise _unresponsive_error(
                crew_id,
                "transport attempted cookie refresh and container restart but "
                "the gateway did not recover",
                crew,
                final_exc if isinstance(final_exc, httpx.HTTPStatusError) else last_exc,
            )

    def _phase2_dead_gateway(
        self,
        crew: dict,
        crew_id: str,
        method: str,
        path: str,
        **kw: Any,
    ) -> Any:
        """Phase 2: connection error — probe then restart only if dead.

        On a connection error from a running container, first probes liveness.
        If the gateway is alive (transient error), retries directly.
        If the gateway is dead, restarts via _ensure_crew_running and retries.

        Returns the API result on success.
        Raises CrewUnresponsiveError if the gateway cannot be recovered.

        Non-idempotent methods (POST, PATCH, DELETE) are NOT retried after a
        gateway restart — the request may have been accepted before the connection
        was cut, and a blind retry would duplicate the side-effect.  The caller
        receives a CrewUnresponsiveError and can choose to retry explicitly.
        """
        _IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "PUT", "OPTIONS"})
        logger.info(
            "Crew %s connection-error phase — probing gateway liveness",
            crew_id,
        )
        crew_url = _crew_url(crew)
        if self.probe(crew_url):
            # Gateway is actually alive — transient error, retry directly
            try:
                return self.request(crew, method, path, **kw)
            except Exception as retry_exc:
                raise _unresponsive_error(
                    crew_id,
                    "gateway responded to liveness probe but API call failed twice",
                    crew, retry_exc,
                )
        logger.info(
            "Crew %s gateway confirmed dead — restarting",
            crew_id,
        )
        try:
            crew = self._restore_crew(crew, crew_id)
        except RuntimeError:
            raise CrewUnresponsiveError(
                f"crew {crew_id} is unresponsive — transport attempted "
                f"container restart but the gateway did not recover. "
                f"Suggestion: check crew status with crews() or try "
                f"again in a moment."
            )
        # TRN-238 QA-2: crew was nuked during the restart — nothing to call against.
        if crew is self._removed_crew:
            raise CrewUnresponsiveError(
                f"crew {crew_id} was removed (nuked) during restart — no longer exists."
            )
        if method.upper() not in _IDEMPOTENT_METHODS:
            raise CrewUnresponsiveError(
                f"crew {crew_id} gateway restarted after a connection reset on a "
                f"{method} request — not retrying a non-idempotent call to avoid "
                f"duplicating side-effects. Re-issue the request to proceed."
            )
        try:
            return self.request(crew, method, path, **kw)
        except Exception as retry_exc:
            raise _unresponsive_error(
                crew_id,
                "transport attempted container restart but the gateway did not recover",
                crew, retry_exc,
            )

    def request_with_recovery(
        self,
        crew: dict,
        crew_id: str,
        method: str,
        path: str,
        **kw: Any,
    ) -> Any:
        """Wrap _crew_api with three-phase recovery logic.

        Phase 0 (task still spawning): On 503 from a per-task /api/spawn/*
        route, KiroCrew's own task record already reports elapsed > 0 before
        the agent process has finished forking/registering enough to serve
        the route. Short bounded retry — this is transient and self-resolving
        within a couple of seconds, not a dead gateway.

        Phase 1 (stale cookie): On 400/401/403 from a running container,
        attempt cookie refresh then retry once.

        Phase 2 (dead gateway): On connection error from a running container,
        confirm via liveness probe then restart via _ensure_crew_running and
        retry once.

        If phase 1 cookie refresh fails, escalates to phase 2.
        At most one retry per failure class — no infinite loops.

        NON-REENTRANT CONTRACT (D1 — do not reintroduce the deadlock):
        This function holds ``_get_recovery_lock(crew_id)`` for the entire call,
        INCLUDING any phase-1/phase-2 sub-call into ``_ensure_crew_running``. The
        per-crew recovery lock is a plain ``threading.Lock`` (non-reentrant), so a
        code path reached *while this lock is held* must NOT call
        ``_crew_api_with_recovery`` again for the same crew — doing so blocks
        forever trying to re-acquire the lock. Concretely: ``_ensure_crew_running``
        (reached via phase 2) calls ``_enroll_crew_members``, which therefore uses
        ``_crew_api`` DIRECTLY (best-effort, its own try/except) and never
        ``_crew_api_with_recovery``. Any new caller of ``_enroll_crew_members`` — or
        any new sub-call added under this lock — must preserve that: route
        gateway calls through ``_crew_api``, not through recovery, so the lock is
        never re-entered. See design.md D1.
        """
        if method == "POST" and path == "/api/spawn":
            kw["json"] = {**kw["json"], "backend": _spawn_backend(crew)}

        lock = self.recovery_lock(crew_id)
        with lock:
            # First attempt
            try:
                return self.request(crew, method, path, **kw)
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status == 503:
                    # ── Phase 0: transient 503 while task process is still starting ──
                    return self._phase0_transient_503(crew, method, path, **kw)
                if status not in (400, 401, 403):
                    raise
                # ── TRN-230: 400 on /continue means session is gone, not a stale cookie.
                # Phase-1 cookie refresh cannot recover a finished session — re-raise so
                # the caller (_steer_captain_checkin) can handle it as "session gone".
                # TRN-238 QA-3: match only a path whose final segment is "continue"
                # (path.endswith("/continue")), not any path merely containing the
                # substring "continue". A route like /api/continue-session/abc or
                # /api/foo?note=continue must NOT trigger this session-gone bypass.
                if status == 400 and path.endswith("/continue"):
                    raise
                # ── Phase 1: stale cookie ─────────────────────────────────────────
                return self._phase1_stale_cookie(
                    crew, crew_id, method, path, trigger_exc=e, **kw
                )

            except (httpx.ConnectError, httpx.ConnectTimeout, ConnectionError, OSError):
                # ── Phase 2: connection error / dead gateway ──────────────────────
                return self._phase2_dead_gateway(crew, crew_id, method, path, **kw)
