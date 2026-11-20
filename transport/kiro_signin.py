"""Transport-side kiro sign-in state for crews.

A kiro crew whose sign-in is unusable does not fail at spawn: ``/api/spawn``
returns a task id and the task fails seconds or minutes later, with an error
that rarely says why (``No profile selected``, or a ``KAS managed MCP
readiness timed out`` caused by a failed auth refresh). The transport owns
these checks so MCP callers never have to probe a crew themselves:

- after launch and wake, :func:`check_in_background` records ``kiro_signin``
  in the crew's registry entry without delaying the launch;
- dispatch paths call :func:`dispatch_guard`, which refuses a crew recorded as
  signed out and returns ``not_authenticated`` with the login command;
- ``pickup`` calls :func:`explain_failure`, which replaces a sign-in-shaped
  task error with ``not_authenticated`` once the check confirms it;
- a successful kiro login calls :func:`clear` for running kiro crews.

"Signed in" means both: the stored kiro credential for the crew's profile
exists and, for IAM Identity Center, carries a Kiro profile; and the crew's
gateway reports kiro-cli authenticated (``GET /api/kiro-prerequisite``). The
gateway alone is not enough: with a profile-less credential it still reports
``authenticated`` while every task fails.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Task error text that a broken kiro sign-in produces.
_AUTH_FAILURE_MARKERS = (
    "No profile selected",
    "Auth refresh callback failed",
    "KAS managed MCP readiness timed out",
    "kiro_prerequisite_required",
)
# A recorded state older than this is re-checked before it blocks a dispatch
# or explains a failure, so a crew fixed out of band recovers on its own.
RECHECK_SECS = 60.0
_PREREQ_TIMEOUT_SECS = 45.0  # the gateway runs kiro-cli to answer; ~12s observed
_GATEWAY_WAIT_SECS = 90

LOGIN_COMMAND = "ghostship auth login kiro"


def _lc():
    try:
        import lifecycle as m  # container (flat /app layout)
    except ModuleNotFoundError:
        from transport import lifecycle as m  # local dev
    return m


def _is_kiro(crew: dict | None) -> bool:
    return bool(crew) and (crew.get("acp_backend") or "kiro") == "kiro"


def looks_like_auth_failure(error: Any) -> bool:
    text = str(error or "")
    return any(marker in text for marker in _AUTH_FAILURE_MARKERS)


def evaluate(crew_id: str, crew: dict) -> dict:
    """Check the crew's kiro sign-in now. Returns ``{"ok", "reason", "checked_at"}``.

    ``ok`` is True (usable), False (not usable, ``reason`` says why) or None
    (could not tell, e.g. the gateway was unreachable).
    """
    lc = _lc()
    now = datetime.now(timezone.utc).isoformat()
    profile = crew.get("acp_profile") or "default"
    try:
        cred = lc._cred_store.get("kiro", profile)
    except Exception as exc:  # store unreadable: say nothing definite
        return {"ok": None, "reason": f"credential store unreadable: {exc}", "checked_at": now}
    if not cred:
        return {"ok": False, "reason": f"no kiro credential is stored for profile '{profile}'",
                "checked_at": now}
    if cred.get("method") == "identity-center" and not lc._auth_payload_has_profile(
        cred.get("payload") or b""
    ):
        return {"ok": False,
                "reason": "the stored IAM Identity Center credential has no Kiro profile",
                "checked_at": now}
    try:
        prereq = lc._crew_api(crew, "GET", "/api/kiro-prerequisite", timeout=_PREREQ_TIMEOUT_SECS)
    except Exception as exc:
        return {"ok": None, "reason": f"could not ask the crew: {exc}", "checked_at": now}
    if not isinstance(prereq, dict) or not prereq.get("authenticated"):
        return {"ok": False, "reason": "kiro-cli in the crew is not signed in", "checked_at": now}
    return {"ok": True, "reason": "", "checked_at": now}


def _registry_entry(crew_id: str) -> dict | None:
    reg = _lc().registry
    with reg:
        entry = reg._reg["crews"].get(crew_id)
        return dict(entry) if entry is not None else None


def record(crew_id: str, state: dict | None) -> None:
    """Store (or with None, remove) ``kiro_signin`` on the crew's registry entry."""
    reg = _lc().registry
    try:
        with reg:
            entry = reg._reg["crews"].get(crew_id)
            if entry is None:
                return
            if state is None:
                entry.pop("kiro_signin", None)
            else:
                entry["kiro_signin"] = state
    except Exception as exc:
        logger.warning("Could not record kiro sign-in state for crew %s: %s", crew_id, exc)


def clear(crew_id: str) -> None:
    record(crew_id, None)


def _fresh(state: dict | None) -> bool:
    if not state or not state.get("checked_at"):
        return False
    try:
        checked = datetime.fromisoformat(state["checked_at"])
    except ValueError:
        return False
    return (datetime.now(timezone.utc) - checked).total_seconds() < RECHECK_SECS


def check_in_background(crew_id: str) -> None:
    """Record the crew's kiro sign-in once its gateway is ready, off the caller's thread."""
    def _run() -> None:
        try:
            crew = _registry_entry(crew_id)
            if not _is_kiro(crew):
                return
            lc = _lc()
            lc._wait_gateway(lc._crew_url(lc._to_crew(crew_id, crew)), timeout=_GATEWAY_WAIT_SECS)
            crew = _registry_entry(crew_id)  # re-read: nuked or updated meanwhile
            if not crew:
                return
            state = evaluate(crew_id, crew)
            if state["ok"] is not None:
                record(crew_id, state)
            if state["ok"] is False:
                logger.warning("Crew %s kiro sign-in not usable: %s", crew_id, state["reason"])
        except Exception:
            logger.debug("Background kiro sign-in check failed for %s", crew_id, exc_info=True)

    threading.Thread(target=_run, daemon=True, name=f"kiro-signin-{crew_id}").start()


def not_authenticated(crew_id: str, reason: str) -> dict:
    return {
        "error": "not_authenticated",
        "backend": "kiro",
        "crew_id": crew_id,
        "message": (
            f"Crew {crew_id}'s kiro sign-in is not usable: {reason}. Run "
            f"`{LOGIN_COMMAND}` (add `--method identity-center` for IAM Identity "
            "Center); a successful sign-in is pushed to running crews."
        ),
        "login_command": LOGIN_COMMAND,
    }


def dispatch_guard(crew_id: str, crew: dict) -> dict | None:
    """Return a ``not_authenticated`` error instead of spawning, or None to proceed.

    Only a crew *recorded* as signed out is refused; unknown state proceeds,
    so the normal path never waits on a probe. A stale "signed out" record is
    re-checked first.
    """
    if not _is_kiro(crew):
        return None
    state = (_registry_entry(crew_id) or {}).get("kiro_signin")
    if not state or state.get("ok") is not False:
        return None
    if not _fresh(state):
        state = evaluate(crew_id, crew)
        if state["ok"] is not None:
            record(crew_id, state)
        if state["ok"] is not False:
            return None
    return not_authenticated(crew_id, state.get("reason", "signed out"))


def explain_failure(crew_id: str, crew: dict | None, error: Any, *, probe: bool = True) -> dict | None:
    """For a failed kiro task whose error looks like a sign-in failure, confirm
    and return ``{"error_code", "error", "upstream_error", "login_command"}``
    to merge into the task payload, or None to leave the error as it is.

    With ``probe=False`` only a recorded state is used (for list views).
    """
    if not _is_kiro(crew) or not looks_like_auth_failure(error):
        return None
    state = (_registry_entry(crew_id) or {}).get("kiro_signin")
    if not _fresh(state):
        if not probe:
            return None
        state = evaluate(crew_id, crew)
        if state["ok"] is not None:
            record(crew_id, state)
    if not state or state.get("ok") is not False:
        return None
    na = not_authenticated(crew_id, state.get("reason", "signed out"))
    return {
        "error_code": "not_authenticated",
        "error": na["message"],
        "upstream_error": str(error),
        "login_command": LOGIN_COMMAND,
    }
