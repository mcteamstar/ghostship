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
from enum import Enum
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


class GatewayAcceptanceUnknown(CrewUnresponsiveError):
    """The gateway may have executed a write whose response was unusable."""


class GatewayRefusal(Enum):
    REJECTED = "rejected"
    STALE_CREDENTIAL = "stale_credential"
    BUSY = "busy"
    SESSION_GONE = "session_gone"
    RESTORE_FAILED = "restore_failed"
    STEER_UNSUPPORTED = "steer_unsupported"
    SESSION_STARTING = "session_starting"


def classify_gateway_refusal(exc: httpx.HTTPStatusError) -> GatewayRefusal:
    try:
        body = exc.response.json()
    except (AttributeError, ValueError):
        body = None
    status = exc.response.status_code
    if not isinstance(body, dict):
        return GatewayRefusal.REJECTED

    code, reason = body.get("code"), body.get("error")
    if (status in (401, 403) and code == "forbidden"
            and getattr(exc.response, "headers", {}).get("X-Auth-Required") == "true"
            and reason in (
        "token expired", "invalid signature", "token superseded", "no active sessions",
        "session revoked", "session ended at gateway restart", "IP mismatch", "no token",
    )):
        return GatewayRefusal.STALE_CREDENTIAL
    if status == 409 and code == "conversation_busy":
        return GatewayRefusal.BUSY
    if status in (400, 404) and code == "conversation_gone":
        return GatewayRefusal.SESSION_GONE
    if status == 502 and code == "steer_failed" and isinstance(reason, str):
        if reason.startswith("steer_unsupported"):
            return GatewayRefusal.STEER_UNSUPPORTED
    if status == 503 and code == "session_starting":
        return GatewayRefusal.SESSION_STARTING
    if code == "resume_failed" or (
        code == "spawn_rejected" and isinstance(reason, str)
        and reason.startswith(("resume_failed:", "RuntimeError: resume_failed:"))
    ):
        return GatewayRefusal.RESTORE_FAILED
    return GatewayRefusal.REJECTED


_NETWORK_ERRORS = (
    getattr(httpx, "RequestError", httpx.ConnectError),
    httpx.ConnectError,
    httpx.ConnectTimeout,
    OSError,
)
_REQUEST_OR_DECODE_ERRORS = (*_NETWORK_ERRORS, ValueError)
_NETWORK_OR_RESTORE_ERRORS = (*_NETWORK_ERRORS, RuntimeError)
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


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

    def _restore(self, crew: dict, crew_id: str) -> dict:
        restored = self._restore_crew(crew, crew_id)
        if restored is self._removed_crew:
            raise CrewUnresponsiveError(f"crew {crew_id} was removed during gateway recovery.")
        return restored

    def _attempt(self, crew: dict, method: str, path: str, **kw: Any) -> Any:
        try:
            response = self.request(crew, method, path, **kw)
        except httpx.HTTPStatusError as exc:
            if method not in _READ_METHODS and exc.response.status_code >= 500:
                refusal = classify_gateway_refusal(exc)
                if method == "POST" and path.endswith("/steer") and refusal in (
                    GatewayRefusal.STEER_UNSUPPORTED, GatewayRefusal.SESSION_STARTING,
                ):
                    raise
                detail, _ = _gateway_error_detail(exc, crew)
                raise GatewayAcceptanceUnknown(
                    f"crew gateway write acceptance is unknown.{detail}"
                ) from None
            raise
        except _REQUEST_OR_DECODE_ERRORS:
            if method not in _READ_METHODS:
                raise GatewayAcceptanceUnknown(
                    "crew gateway write acceptance is unknown; reconcile before retrying."
                ) from None
            raise

        if method == "POST" and (path == "/api/spawn" or path.endswith("/continue")):
            task_id = response.get("id") if isinstance(response, dict) else None
            if not isinstance(task_id, str) or not task_id:
                raise GatewayAcceptanceUnknown(
                    "crew gateway accepted the request without a usable task ID; reconcile before retrying."
                )
        return response

    def request_with_recovery(
        self, crew: dict, crew_id: str, method: str, path: str, **kw: Any,
    ) -> Any:
        """Retry once after a recoverable read failure or explicit auth refusal.

        Hold the per-crew lock across recovery. Restoration must use one-shot
        gateway requests during enrollment to avoid re-entering the lock.
        """
        method = method.upper()
        if method == "POST" and path == "/api/spawn":
            kw["json"] = {**kw["json"], "backend": _spawn_backend(crew)}

        with self.recovery_lock(crew_id):
            try:
                return self._attempt(crew, method, path, **kw)
            except httpx.HTTPStatusError as exc:
                if classify_gateway_refusal(exc) is GatewayRefusal.STALE_CREDENTIAL:
                    try:
                        if not self._refresh_cookie(crew, crew_id):
                            crew = self._restore(crew, crew_id)
                    except RuntimeError:
                        raise _unresponsive_error(crew_id, "credential recovery failed", crew, exc) from None
                elif method != "GET" or exc.response.status_code != 503:
                    raise
                else:
                    time.sleep(1)
            except _NETWORK_ERRORS as exc:
                try:
                    if not self.probe(_crew_url(crew)):
                        crew = self._restore(crew, crew_id)
                except _NETWORK_OR_RESTORE_ERRORS:
                    raise _unresponsive_error(crew_id, "gateway restoration failed", crew, exc) from None

            try:
                return self._attempt(crew, method, path, **kw)
            except _NETWORK_ERRORS as exc:
                raise _unresponsive_error(crew_id, "gateway call failed after recovery", crew, exc) from None
