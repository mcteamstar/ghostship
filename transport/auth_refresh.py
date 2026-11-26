"""Operator refresh of one existing crew's assigned credential (TRN-367).

``refresh_crew_auth`` is the single operation behind both transport routes,
``POST /crews/{crew_id}/auth/refresh`` (bearer-protected operator clients) and
``POST /internal/crews/{crew_id}/auth/refresh`` (Radar, via ``X-Transport-Token``).
It takes no input but the crew id: the credential is always the one stored for
the backend and profile recorded in the crew's registry entry, so a caller can
neither choose nor supply a credential.

Every outcome is a normal result of an operation that ran and is returned as a
dict whose ``status`` is one of ``OUTCOMES``; only an unknown crew raises
(``CrewNotFound``). The operation never starts, stops or recreates a crew.

Secret handling: the dict returned holds the crew id, backend, profile and a
fixed guidance message, never a credential. Failures are logged by exception
class only. Exception text from the container runtime can echo inspect output
(which includes the container's environment) or exec output, so it is neither
logged, nor passed to ``exc_info``, nor returned.

Dual-path import pattern: the container deploys ``transport/*.py`` flat under
``/app``, so every sibling import tries the flat name first.
"""

from __future__ import annotations

import logging

try:
    import login as _login  # container: flat /app/
except ModuleNotFoundError:
    from transport import login as _login  # local dev

try:
    from registry import _get_crew  # container: flat /app/
except ModuleNotFoundError:
    from transport.registry import _get_crew  # local dev

try:
    from podman import _get_podman  # container: flat /app/
except ModuleNotFoundError:
    from transport.podman import _get_podman  # local dev

logger = logging.getLogger(__name__)

REFRESHED = "refreshed"
PENDING_ON_WAKE = "pending_on_wake"
CURRENT = "current"
RECREATE_REQUIRED = "recreate_required"
CREDENTIAL_MISSING = "credential_missing"
REFRESH_FAILED = "refresh_failed"

OUTCOMES = (
    REFRESHED,
    PENDING_ON_WAKE,
    CURRENT,
    RECREATE_REQUIRED,
    CREDENTIAL_MISSING,
    REFRESH_FAILED,
)

# Login-flow methods: the credential is written into the crew's home, so a
# running crew can be refreshed in place and a stopped one picks it up on wake.
_FLOW_METHODS = frozenset({
    ("kiro", "builder-id"),
    ("kiro", "identity-center"),
    ("claude", "oauth"),
    ("codex", "chatgpt"),
})


class CrewNotFound(KeyError):
    """The crew id is not in the registry."""


def _launcher():
    try:
        import launcher as m  # container: flat /app/
    except ModuleNotFoundError:
        from transport import launcher as m  # local dev
    return m


def _lifecycle():
    try:
        import lifecycle as m  # container: flat /app/
    except ModuleNotFoundError:
        from transport import lifecycle as m  # local dev
    return m


def _kiro_signin():
    try:
        import kiro_signin as m  # container: flat /app/
    except ModuleNotFoundError:
        from transport import kiro_signin as m  # local dev
    return m


def _crew_record(crew_id: str) -> dict:
    try:
        return _get_crew(crew_id)
    except KeyError as exc:
        raise CrewNotFound(crew_id) from exc


def _login_command(backend: str, profile: str) -> str:
    command = f"ghostship auth login {backend}"
    return command if profile == "default" else f"{command} --profile {profile}"


def _recreate_message(running: bool) -> str:
    # Both paths end in the workspace-preserving evac -> nuke -> launch -> supply
    # workflow documented in docs/auth.md. A stopped crew cannot be woken for
    # evac while the stored credential differs from its container, so that case
    # says to restore the launch-time credential first.
    if running:
        return (
            "The stored credential or its method differs from this crew's launch-time "
            "container environment, which cannot be changed in place. Save the "
            "workspace with evac, nuke the crew, then launch a replacement and "
            "supply the saved workspace. See docs/auth.md."
        )
    return (
        "The stored credential or its method differs from this crew's launch-time "
        "container environment, so the crew cannot wake. Restore the credential the "
        "crew was launched with, wake the crew and run evac, then nuke it, launch a "
        "replacement and supply the saved workspace. See docs/auth.md."
    )


def _log_failure(crew_id: str, step: str, exc: BaseException) -> None:
    """Record a failed step without the exception text, traceback or any value."""
    logger.warning(
        "Crew %s auth refresh: %s failed (%s)", crew_id, step, type(exc).__name__,
    )


def _inject(podman, container: str, backend: str, credential: dict) -> None:
    """Write a stored login-flow credential into a running crew's container."""
    lifecycle = _lifecycle()
    if backend == "kiro":
        payload = credential["payload"]
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        lifecycle._inject_auth(podman, container, payload)
        return
    archive = _launcher()._oauth_archive(credential)
    if backend == "claude":
        lifecycle._inject_claude_auth(podman, container, archive)
    else:
        lifecycle._inject_codex_auth(podman, container, archive)


def _forget_kiro_signin(crew_id: str, backend: str) -> None:
    """Drop the crew's cached kiro sign-in state so dispatch re-checks it."""
    if backend != "kiro":
        return
    try:
        _kiro_signin().clear(crew_id)
    except Exception as exc:  # best effort: the credential is already injected
        logger.debug("Crew %s: kiro sign-in state not cleared (%s)", crew_id, type(exc).__name__)


def refresh_crew_auth(crew_id: str) -> dict:
    """Refresh the credential assigned to *crew_id*; returns the outcome dict.

    Blocking (registry, credential store and container runtime calls); async
    callers run it in a worker thread. Raises ``CrewNotFound`` for an unknown
    crew and nothing else.
    """
    _crew_record(crew_id)  # unknown crew: answer before touching the credential lock
    # Credential replacement and logout hold this lock for their whole commit.
    # Taking it here means the stored profile read below is the committed one
    # and cannot change before the injection that uses it, so a concurrent
    # change cannot be overwritten with the credential it just replaced.
    with _login._credential_transaction_lock:
        crew = _crew_record(crew_id)  # status may have changed while waiting
        result = _refresh_locked(crew_id, crew)
    logger.info(
        "Crew %s auth refresh (%s profile %s): %s",
        crew_id, result["backend"], result["profile"], result["status"],
    )
    return result


def _refresh_locked(crew_id: str, crew: dict) -> dict:
    backend = crew.get("acp_backend") or "kiro"
    profile = crew.get("acp_profile") or "default"
    container = crew.get("container") or ""
    running = crew.get("status") == "running"

    def outcome(status: str, message: str) -> dict:
        return {
            "status": status,
            "crew_id": crew_id,
            "backend": backend,
            "profile": profile,
            "message": message,
        }

    try:
        credential = _login._cred_store.get(backend, profile)
    except Exception as exc:
        _log_failure(crew_id, "credential read", exc)
        return outcome(
            REFRESH_FAILED,
            "The stored credential could not be read. The crew was not changed. "
            "Check the transport log, then retry.",
        )
    if credential is None:
        return outcome(
            CREDENTIAL_MISSING,
            f"No credential is stored for {backend} profile '{profile}'. Run "
            f"`{_login_command(backend, profile)}`, then refresh again.",
        )

    method = credential.get("method")
    launcher = _launcher()
    static = launcher.is_static_credential(backend, method)
    if not static and (backend, method) not in _FLOW_METHODS:
        return outcome(
            REFRESH_FAILED,
            f"The stored {backend} credential uses a method this version cannot "
            f"refresh. Run `{_login_command(backend, profile)}` to store it again.",
        )

    # Static values are fixed in the container's environment, so the container is
    # always compared with the stored credential first. For a login-flow
    # credential this finds a static value left over from a previous method,
    # which keeps overriding the flow credential until the crew is recreated.
    try:
        mismatch = launcher.static_credential_mismatch(
            _get_podman(), container, backend, credential,
        )
    except Exception as exc:
        _log_failure(crew_id, "static credential comparison", exc)
        return outcome(
            REFRESH_FAILED,
            "The stored credential could not be compared with the crew's container. "
            "The crew was not changed. Check the transport log, then retry.",
        )
    if mismatch is not None:
        return outcome(RECREATE_REQUIRED, _recreate_message(running))
    if static:
        return outcome(
            CURRENT,
            "The crew's container already carries the stored static credential. "
            "Nothing to change.",
        )

    if not running:
        return outcome(
            PENDING_ON_WAKE,
            "The crew is stopped. Its stored credential is injected the next time it wakes.",
        )
    try:
        _inject(_get_podman(), container, backend, credential)
    except Exception as exc:
        _log_failure(crew_id, "credential injection", exc)
        return outcome(
            REFRESH_FAILED,
            "The stored credential could not be injected into the running crew. "
            "The crew was left running. Check the transport log, then retry.",
        )
    _forget_kiro_signin(crew_id, backend)
    return outcome(REFRESHED, "The current stored credential was injected into the running crew.")
