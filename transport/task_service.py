"""Dispatch, steer, and pickup operations shared by Transport adapters."""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx2 as httpx

try:
    from captain import _read_all_mail_counts, _read_all_mail_subjects, _skim_all_mailboxes
    from constants import PERSONA_NAMES
    from crew import Crew
    from crew_gateway import CrewUnresponsiveError, _gateway_error_detail, _unresponsive_error
    from podman import PodmanClient
    from registry import _find_batch_by_task_ids, _update_batch_status, _write_batch
except ModuleNotFoundError:
    from .captain import _read_all_mail_counts, _read_all_mail_subjects, _skim_all_mailboxes
    from .constants import PERSONA_NAMES
    from .crew import Crew
    from .crew_gateway import CrewUnresponsiveError, _gateway_error_detail, _unresponsive_error
    from .podman import PodmanClient
    from .registry import _find_batch_by_task_ids, _update_batch_status, _write_batch

logger = logging.getLogger(__name__)
PERSONA_ALLOWLIST = frozenset(PERSONA_NAMES)
_BATCH_POLL_INTERVAL_SECS = 3

_MODEL_MAX_LENGTH = 500
_MODEL_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def _validate_model(model: str | None) -> str | None:
    """Validate and normalize an optional KiroCrew model override."""
    if model is None:
        return None
    if not isinstance(model, str):
        raise ValueError("Invalid model: expected a string")
    if not model:
        return None
    if len(model) > _MODEL_MAX_LENGTH:
        raise ValueError(
            f"Invalid model: maximum length is {_MODEL_MAX_LENGTH} characters"
        )
    if _MODEL_NAME_RE.fullmatch(model) is None:
        raise ValueError(
            "Invalid model: must start with a letter or digit and contain only "
            "letters, digits, '.', '_' or '-'"
        )
    return model


def _response_body(exc: httpx.HTTPStatusError) -> str:
    try:
        return exc.response.text or ""
    except Exception:
        return ""


def _is_steer_unsupported(exc: httpx.HTTPStatusError) -> bool:
    """True when the run's backend refuses a mid-turn interrupt (claude, codex).

    KiroCrew answers 502 ``steer_failed`` with a ``steer_unsupported`` detail and
    asks for ``mode='follow_up'`` instead.
    """
    return exc.response.status_code == 502 and "steer_unsupported" in _response_body(exc)


def _is_not_running(exc: httpx.HTTPStatusError) -> bool:
    """True when the run finished between our status check and the steer (409 not_running)."""
    return exc.response.status_code == 409 and "not_running" in _response_body(exc)


def _is_session_starting(exc: httpx.HTTPStatusError) -> bool:
    """True when the run is alive but its session hasn't registered yet (503 session_starting)."""
    return exc.response.status_code == 503 and "session_starting" in _response_body(exc)


def _resolve_dispatch_slot(
    agent: str,
    slot: bool | None,
    crew,
) -> tuple[str | None, str | None]:
    """Resolve the effective slot and parent_session for a dispatch.

    Returns (effective_slot, parent_session).

    Two modes:

    - ``slot=None`` (default): let the system decide. An enrolled agent routes
      to its member DM slot (``parent_session="dashboard:member-<slug>"``),
      echoing ``"<slug>"`` as the slot name. An unenrolled agent routes headless
      (``(None, None)``) — no session is created.
    - ``slot=False``: explicit headless, regardless of enrollment —
      ``(None, None)``.

    ``True`` is a legacy value, not a distinct slot mode. It logs a warning
    and is treated as ``None``: enrolled agents use their member slot, while
    unenrolled agents remain headless. MCP callers cannot pass string-valued
    slots because the dispatch tool schema accepts only boolean or null.
    """
    if isinstance(crew, Crew):
        enrolled: frozenset[str] = frozenset(crew.enrolled_agents or [])
    else:
        enrolled = frozenset(crew.get("enrolled_agents") or [])
    if slot is True:
        logger.warning(
            "_resolve_dispatch_slot: slot=True is not a valid value; "
            "treating as slot=None (member-slot or headless resolution proceeds normally)"
        )
        slot = None
    if slot is None and agent in enrolled:
        # Echo the agent name (clean) not "member-<agent>" (implementation detail).
        return agent, f"dashboard:member-{agent}"
    # slot=None for an unenrolled agent, or slot=False for anyone → headless.
    return None, None


class TaskService:
    """Own task orchestration and process-local pickup timestamps."""

    def __init__(
        self, *, config, require_crew, ensure_running, to_crew, validate_agent,
        call_gateway, get_podman, sign_in, record_last_task_at,
        write_batch=_write_batch, find_batch=_find_batch_by_task_ids,
        update_batch_status=_update_batch_status, read_mail_counts=_read_all_mail_counts,
        read_mail_subjects=_read_all_mail_subjects, skim_mailboxes=_skim_all_mailboxes,
    ) -> None:
        self.config = config
        self.require_crew = require_crew
        self.ensure_running = ensure_running
        self.to_crew = to_crew
        self.validate_agent = validate_agent
        self.call_gateway = call_gateway
        self.get_podman = get_podman
        self.sign_in = sign_in
        self.record_last_task_at = record_last_task_at
        self.write_batch = write_batch
        self.find_batch = find_batch
        self.update_batch_status = update_batch_status
        self.read_mail_counts = read_mail_counts
        self.read_mail_subjects = read_mail_subjects
        self.skim_mailboxes = skim_mailboxes
        self._task_timestamps: dict[str, dict] = {}
        self._task_timestamps_lock = threading.Lock()

    def _expire_completed(self, now: datetime) -> None:
        cutoff = (now - timedelta(seconds=self.config.ga_task_timestamp_ttl_secs)).isoformat()
        expired = [
            task_id for task_id, stamps in self._task_timestamps.items()
            if stamps.get("completed_at") is not None and stamps["completed_at"] < cutoff
        ]
        for task_id in expired:
            del self._task_timestamps[task_id]

    def _record_dispatch(
        self, crew_id: str | None, task_id: str, *, batch: bool = False,
    ) -> str:
        created_at = datetime.now(timezone.utc).isoformat()
        stamps = {"created_at": created_at, "started_at": None, "completed_at": None}
        if batch:
            stamps["status"] = "pending"
        with self._task_timestamps_lock:
            self._task_timestamps[task_id] = stamps
        self.record_last_task_at(crew_id, created_at)
        return created_at

    @staticmethod
    def _spawn_payload(task: str | None, agent: str, model: str | None, parent_session: str | None) -> dict:
        body: dict[str, Any] = {"task": task, "agent": agent, "keep": True}
        if model is not None:
            body["model"] = model
        if parent_session is not None:
            body["parent_session"] = parent_session
        return body

    def dispatch(
        self,
        task: str | None = None,
        agent: str = "ghost",
        crew_id: str | None = None,
        model: str | None = None,
        tasks: list[str] | None = None,
        slot: bool | None = None,
    ) -> dict:
        # Mutual-exclusion + presence guard (task 2.2).
        if task is not None and tasks is not None:
            return {"error": "Provide either task or tasks, not both"}
        if task is None and tasks is None:
            return {"error": "Provide task or tasks"}

        try:
            model = _validate_model(model)
        except ValueError as e:
            return {"error": str(e)}
        try:
            self.validate_agent(agent)
        except ValueError as e:
            return {"error": str(e)}

        if tasks is not None:
            return self._dispatch_batch(tasks, agent, crew_id, model, slot=slot)

        try:
            crew = self.ensure_running(self.require_crew(crew_id), crew_id)
        except (ValueError, KeyError, RuntimeError) as e:
            return {"error": str(e)}

        if (denied := self.sign_in().dispatch_guard(crew_id, crew)) is not None:
            return denied

        effective_slot, parent_session = _resolve_dispatch_slot(agent, slot, crew)

        body = self._spawn_payload(task, agent, model, parent_session)

        try:
            result = self.call_gateway(
                crew, crew_id, "POST", "/api/spawn",
                json=body,
            )
        except CrewUnresponsiveError as e:
            return {"error": str(e)}
        except httpx.HTTPStatusError as exc:
            detail, _ = _gateway_error_detail(exc, crew)
            return {"error": f"crew gateway rejected dispatch.{detail}"}

        task_id = result.get("id")
        if not task_id:
            return {"error": "spawn returned no task id"}
        created_at = self._record_dispatch(crew_id, task_id)

        response: dict[str, Any] = {
            "task_id": task_id,
            "crew_id": crew_id,
            "status": "dispatched",
            "task": task,
            "agent": agent,
            "slot": effective_slot,
            "created_at": created_at,
        }
        return response

    def steer(
        self,
        task_id: str,
        message: str,
        crew_id: str | None = None,
        force: bool = False,
    ) -> dict:
        try:
            crew = self.ensure_running(self.require_crew(crew_id), crew_id)
        except (ValueError, KeyError, RuntimeError) as e:
            return {"error": str(e)}

        def _continue(action: str, what: str) -> dict:
            r, err, _ = self._steer_call(crew, crew_id, "POST", f"/api/spawn/{task_id}/continue",
                                    what, json={"task": message})
            if err:
                return err
            return {"task_id": r.get("id", task_id), "crew_id": crew_id,
                    "action": action, "message": message}

        s, err, _ = self._steer_call(crew, crew_id, "GET", f"/api/spawn/{task_id}",
                                f"status lookup for task {task_id}")
        if err:
            return err
        if s.get("done", False):
            return _continue("redeployed", f"continue for finished task {task_id}")
        if force:
            _, err, _ = self._steer_call(crew, crew_id, "DELETE", f"/api/spawn/{task_id}",
                                    f"force stop of task {task_id}")
            if err:
                return err
            return _continue(
                "force_redeployed",
                f"resume of task {task_id} after force stop (the task is stopped and was not resumed)",
            )

        path = f"/api/spawn/{task_id}/steer"
        _, err, exc = self._steer_call(crew, crew_id, "POST", path,
                                  f"steer for running task {task_id}", json={"message": message})
        if exc is not None and _is_not_running(exc):
            # Finished between the status check and the steer: continue it instead.
            return _continue("redeployed", f"continue for finished task {task_id}")
        if exc is not None and _is_steer_unsupported(exc):
            # The backend can't interrupt mid-turn: queue the message for delivery
            # as a continuation once the current turn ends.
            _, err, exc = self._steer_call(crew, crew_id, "POST", path,
                                      f"follow-up for running task {task_id}",
                                      json={"message": message, "mode": "follow_up"})
            if exc is not None and _is_not_running(exc):
                return _continue("redeployed", f"continue for finished task {task_id}")
            if err:
                return err
            return {"task_id": task_id, "crew_id": crew_id, "action": "follow_up_queued",
                    "message": message,
                    "note": "This backend can't interrupt a running turn; the message is "
                            "delivered as a new continuation task when the current turn ends "
                            "(see pickup(crew_id=...)). Use force=True to stop it now."}
        if err:
            if exc is not None and _is_session_starting(exc):
                err["hint"] = ("The task's session is still starting; retry once it has made "
                               "a tool call. force=True would stop it instead.")
            elif exc is not None:
                err["hint"] = "steer(..., force=True) stops the task and resumes its session with the message."
            return err
        return {"task_id": task_id, "crew_id": crew_id, "action": "steered", "message": message}

    def pickup(
        self,
        task_id: str | None = None,
        crew_id: str | None = None,
        timeout_secs: int = 0,
        agent: str | None = None,
        task_ids: list[str] | None = None,
    ) -> dict | list:
        # Batch mutual-exclusion + empty guards (tasks 4.2, 4.3).
        if task_id is not None and task_ids is not None:
            return {"error": "Provide either task_id or task_ids, not both"}
        if task_ids is not None and len(task_ids) == 0:
            return {"error": "task_ids must not be empty"}

        try:
            crew = self.ensure_running(self.require_crew(crew_id), crew_id)
        except (ValueError, KeyError, RuntimeError) as e:
            return {"error": str(e)}

        try:
            podman = self.get_podman()
        except Exception as e:
            return {"error": str(e)}

        container = self.to_crew(crew_id, crew).container
        effective_timeout = min(max(0, timeout_secs), 30) if timeout_secs > 0 else 0

        if task_ids is not None:
            batch_record = self.find_batch(crew_id, task_ids)
            found_batch_id = batch_record["batch_id"] if batch_record else None
            return self._pickup_batch(
                crew, crew_id, task_ids, podman, container, effective_timeout,
                self._pickup_single, self.read_mail_counts,
                batch_id=found_batch_id,
                update_batch_status=self.update_batch_status,
            )

        if task_id:
            return self._pickup_single(crew, crew_id, task_id, podman, container, effective_timeout)
        if agent is not None:
            # Agent filter: validate and return single-inbox subjects only
            if agent not in PERSONA_ALLOWLIST:
                return {
                    "error": (
                        f"Invalid agent {agent!r}. Must be one of: "
                        + ", ".join(sorted(PERSONA_ALLOWLIST))
                    )
                }
            all_subjects = self.skim_mailboxes(podman, container)
            subjects = all_subjects.get(agent, [])
            return {
                "agent": agent,
                "subjects": subjects,
                "mail": len(subjects),
            }
        return self._pickup_list(crew, crew_id, podman, container, effective_timeout)

    def _steer_call(
        self,
        crew: dict, crew_id: str, method: str, path: str, what: str, **kw: Any,
    ) -> tuple[Any, dict | None, httpx.HTTPStatusError | None]:
        """Make one gateway call for steer without letting it raise.

        Returns ``(response, None, None)`` on success, or ``(None, error, exc)`` where
        ``error`` is the caller-facing dict and ``exc`` is the gateway's
        HTTPStatusError (``None`` when the crew was unresponsive instead).
        """
        try:
            return self.call_gateway(crew, crew_id, method, path, **kw), None, None
        except CrewUnresponsiveError as e:
            return None, {"error": str(e)}, None
        except httpx.HTTPStatusError as e:
            detail, _ = _gateway_error_detail(e, crew)
            return None, {"error": f"crew gateway rejected {what}.{detail}"}, e

    def _dispatch_batch(
        self,
        tasks: list[str],
        agent: str,
        crew_id: str | None,
        model: str | None,
        slot: bool | None = None,
    ) -> dict:
        """Sequentially dispatch a batch of tasks; record a batch entry.

        Validation (size, agent, model) has already run in ``dispatch``. On the
        first CrewUnresponsiveError or unexpected failure the loop breaks and a
        ``partial`` batch is recorded with the task_ids assigned so far.

        ``slot`` follows the same two-mode semantics as single-task dispatch:
        ``None`` (default) routes an enrolled agent to its shared member DM slot and
        an unenrolled agent headless; ``False`` is explicit headless for everyone.
        All tasks in the batch share the one resolved slot (member or headless);
        per-task slot names are not generated.
        """
        # Size validation.
        max_tasks = self.config.ga_batch_max_tasks
        if len(tasks) == 0 or len(tasks) == 1:
            return {"error": "tasks must contain at least 2 items; use task= for a single dispatch"}
        if len(tasks) > max_tasks:
            return {"error": f"tasks exceeds maximum batch size of {max_tasks}"}

        try:
            crew = self.ensure_running(self.require_crew(crew_id), crew_id)
        except (ValueError, KeyError, RuntimeError) as e:
            return {"error": str(e)}

        if (denied := self.sign_in().dispatch_guard(crew_id, crew)) is not None:
            return denied

        # Resolve effective slot and shared parent_session using the unified helper.
        # effective_slot is either the agent name (member slot) or None (headless);
        # all tasks in the batch share the one resolved parent_session.
        effective_slot, shared_parent_session = _resolve_dispatch_slot(agent, slot, crew)

        batch_id = str(uuid.uuid4())
        task_ids: list[str] = []
        now = datetime.now(timezone.utc)
        created_at = now.isoformat()
        dispatch_error: str | None = None

        for task in tasks:
            body = self._spawn_payload(task, agent, model, shared_parent_session)
            try:
                result = self.call_gateway(
                    crew, crew_id, "POST", "/api/spawn", json=body,
                )
            except httpx.HTTPStatusError as e:
                # A non-retryable gateway response (for example, a 4xx refusal)
                # bypasses recovery as an HTTPStatusError. Convert it at the batch
                # boundary so accepted members still reach the shared finalizer,
                # and use the existing sanitizer before surfacing gateway detail.
                dispatch_error = str(
                    _unresponsive_error(crew_id, "gateway refused batch spawn", crew, e)
                )
                break
            except (CrewUnresponsiveError, RuntimeError, ValueError) as e:
                dispatch_error = str(e)
                break
            tid = result.get("id")
            if not tid:
                dispatch_error = "spawn returned no task id"
                break
            task_ids.append(tid)
            self._record_dispatch(crew_id, tid, batch=True)

        # Echo the effective slot: the agent name (member slot) or None (headless).
        response_slot: str | None = effective_slot

        if dispatch_error is None:
            # Task 2.5: full success.
            self.write_batch(crew_id, batch_id, task_ids, status="pending", created_at=created_at)
            response: dict[str, Any] = {
                "batch_id": batch_id,
                "task_ids": task_ids,
                "crew_id": crew_id,
                "status": "dispatched",
                "agent": agent,
                "slot": response_slot,
                "created_at": created_at,
            }
            return response

        if not task_ids:
            # Nothing was accepted, so retain the existing simple failure shape
            # and avoid persisting an empty batch record.
            return {"error": dispatch_error}

        # Task 2.6: partial failure. Record what was started; surface the error.
        self.write_batch(crew_id, batch_id, task_ids, status="partial", created_at=created_at)
        response = {
            "batch_id": batch_id,
            "task_ids": task_ids,
            "crew_id": crew_id,
            "status": "partial",
            "agent": agent,
            "slot": response_slot,
            "created_at": created_at,
            "error": dispatch_error,
        }
        return response

    def _pickup_batch(
        self,
        crew: dict,
        crew_id: str,
        task_ids: list[str],
        podman: "PodmanClient",
        container: str,
        timeout_secs: int,
        pickup_single,
        read_all_mail_counts,
        batch_id: str | None = None,
        update_batch_status=None,
    ) -> dict:
        """Blocking multi-task pickup: collect results for every id in *task_ids*.

        Orchestrates per-round sequential calls to ``pickup_single(timeout_secs=0)``
        for each task id, aggregating into a dict keyed by task_id. The whole call
        is capped at ``self.config.ga_pickup_max_poll_secs`` of wall time (each round polls all
        members once, then sleeps 3 s). A task the gateway does not know about (404
        / missing) is marked ``{"done": false, "lost": true, ...}`` rather than
        raising, so the other members' results survive.

        ``pickup_single`` and ``read_all_mail_counts`` are supplied by the service
        or a compatibility caller. ``update_batch_status``
        (optional) is called with (crew_id, batch_id, "complete") when every task is
        done and a ``batch_id`` is known.

        Response shape::

            {
              "<task_id>": {<single-task pickup shape> | lost-marker},
              ...,
              "done": bool,          # True only when every member is done
              "completed_tasks": int,
              "total_tasks": int,
              "reason": "timeout" | "admiral_mail",   # only when it applies
            }
        """
        total = len(task_ids)

        # Cap the batch wall time at self.config.ga_pickup_max_poll_secs regardless of the
        # requested timeout — identical to the single-task internal cap contract.
        capped_timeout = min(max(0, timeout_secs), self.config.ga_pickup_max_poll_secs)

        # Admiral-mail early-return baseline read before the first round.
        if capped_timeout > 0:
            initial_counts = read_all_mail_counts(podman, container)
            initial_admiral_mail = initial_counts.get("admiral", 0)
        else:
            initial_admiral_mail = 0

        deadline = time.monotonic() + capped_timeout

        def _poll_round() -> tuple[dict, int]:
            """Poll every task once; return (results, done_count)."""
            results: dict[str, Any] = {}
            done_count = 0
            for tid in task_ids:
                try:
                    res = pickup_single(crew, crew_id, tid, podman, container, 0)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 404:
                        raise
                    res = {"error": "task not found in gateway"}
                # Lost member: gateway returns 404 for an unknown task id. The
                # single-task path surfaces that as an error string; normalise it
                # to an explicit lost marker so the batch survives.
                err = res.get("error", "") if isinstance(res, dict) else ""
                if err and ("404" in str(err) or "not found" in str(err).lower()):
                    res = {
                        "task_id": tid,
                        "done": False,
                        "lost": True,
                        "error": "task not found in gateway",
                    }
                results[tid] = res
                if res.get("done"):
                    done_count += 1
                    # Per-task status (H-3): mark the task complete in
                    # self._task_timestamps so callers polling pickup can observe
                    # per-task completion within this process session.
                    with self._task_timestamps_lock:
                        if tid in self._task_timestamps:
                            self._task_timestamps[tid]["status"] = "complete"
                            if self._task_timestamps[tid]["completed_at"] is None:
                                self._task_timestamps[tid]["completed_at"] = datetime.now(timezone.utc).isoformat()
            return results, done_count

        while True:
            results, done_count = _poll_round()
            all_done = done_count == total and total > 0

            out: dict[str, Any] = dict(results)
            out["done"] = all_done
            out["completed_tasks"] = done_count
            out["total_tasks"] = total

            if all_done:
                if batch_id is not None and update_batch_status is not None:
                    try:
                        update_batch_status(crew_id, batch_id, "complete")
                    except Exception as exc:  # best-effort; do not fail the pickup
                        logger.warning(
                            "Could not mark batch %s complete: %s",
                            batch_id, exc,
                        )
                return out

            # Snapshot mode (timeout_secs == 0): one query per task, no blocking.
            if capped_timeout == 0:
                return out

            # Admiral-mail early-return: re-read the count and bail if it grew.
            admiral_mail = read_all_mail_counts(podman, container).get("admiral", 0)
            if admiral_mail > initial_admiral_mail:
                out["reason"] = "admiral_mail"
                return out

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                out["reason"] = "timeout"
                return out

            time.sleep(min(_BATCH_POLL_INTERVAL_SECS, remaining))

    def _pickup_single(
        self,
        crew: dict,
        crew_id: str,
        task_id: str,
        podman: PodmanClient,
        container: str,
        timeout_secs: int,
    ) -> dict:
        """Single-task pickup with optional polling and mail state."""
        # Capture initial admiral mail count for early-return detection using a
        # single batched exec rather than a dedicated _mail_count call.
        if timeout_secs > 0:
            initial_counts = self.read_mail_counts(podman, container)
            initial_admiral_mail = initial_counts.get("admiral", 0)
        else:
            initial_admiral_mail = 0
        deadline = time.monotonic() + timeout_secs

        while True:
            try:
                r = self.call_gateway(crew, crew_id, "GET", f"/api/spawn/{task_id}")
            except CrewUnresponsiveError as e:
                return {"error": str(e), "task_id": task_id, "crew_id": crew_id}
            done = r.get("done", False)

            # Single exec reads all mailboxes at once.
            mail_counts = self.read_mail_counts(podman, container)
            mail_subjects = self.read_mail_subjects(podman, container)
            agent_persona = r.get("agent", "")
            agent_mail = mail_counts.get(agent_persona, 0) if agent_persona else 0
            admiral_mail = mail_counts.get("admiral", 0)

            # Populate task timestamps
            now = datetime.now(timezone.utc)
            with self._task_timestamps_lock:
                ts = self._task_timestamps.get(task_id, {})
                elapsed = r.get("elapsed", 0)
                if ts and elapsed and elapsed > 0 and ts.get("started_at") is None:
                    ts["started_at"] = now.isoformat()
                if ts and done and ts.get("completed_at") is None:
                    ts["completed_at"] = now.isoformat()
                # Snapshot ts under the lock so the post-lock reads below see a stable
                # copy rather than a live reference that a concurrent self._pickup_single
                # or self._dispatch_batch could mutate after release.
                ts = dict(ts)

                self._expire_completed(now)

            out: dict[str, Any] = {
                "task_id": r.get("id"),
                "crew_id": crew_id,
                "done": done,
                "turns": r.get("turns", 0),
                "last_tool": r.get("last_tool", ""),
                "elapsed_secs": int(r.get("elapsed", 0)),
                "result": r.get("result", ""),
                "error": r.get("error", ""),
                "outcome": r.get("outcome", ""),
                "agent_mail": agent_mail,
                "created_at": ts.get("created_at") if ts else None,
                "started_at": ts.get("started_at") if ts else None,
                "completed_at": ts.get("completed_at") if ts else None,
            }
            if done and out["error"]:
                explained = self.sign_in().explain_failure(crew_id, crew, out["error"])
                if explained:
                    out.update(explained)

            # Include subject lines for the agent persona, raven, captain, and admiral.
            # captain/admiral come from the single self.read_mail_subjects exec above
            # (same shape: [{subject, received_at}]). The admiral_mail count above is
            # still used for the reason="admiral_mail" early-return signal.
            if agent_persona:
                out[f"{agent_persona}_subjects"] = mail_subjects.get(agent_persona, [])
            raven_subjects = mail_subjects.get("raven", [])
            if raven_subjects:
                out["raven_subjects"] = raven_subjects
            captain_subjects = mail_subjects.get("captain", [])
            admiral_subjects = mail_subjects.get("admiral", [])
            out["captain_subjects"] = captain_subjects
            out["captain_mail"] = len(captain_subjects)
            out["admiral_subjects"] = admiral_subjects
            out["admiral_mail"] = len(admiral_subjects)

            if done or timeout_secs == 0:
                return out

            # Check for admiral mail early-return
            if admiral_mail > initial_admiral_mail:
                out["reason"] = "admiral_mail"
                return out

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if not done:
                    out["reason"] = "timeout"
                return out

            # F-03 audit: @mcp.tool() handlers are dispatched via run_in_executor
            # (confirmed: MCPServer.streamable_http_app wraps sync handlers in the
            # default thread-pool executor). time.sleep blocks the worker thread,
            # not the event loop — safe, no conversion to asyncio.sleep needed.
            time.sleep(min(3, remaining))

    def _pickup_list(
        self,
        crew: dict,
        crew_id: str,
        podman: PodmanClient,
        container: str,
        timeout_secs: int,
    ) -> dict:
        """List-all pickup with optional polling and mail state."""
        # Capture initial admiral mail count for early-return detection using a
        # single batched exec rather than a dedicated _mail_count call.
        if timeout_secs > 0:
            initial_counts = self.read_mail_counts(podman, container)
            initial_admiral_mail = initial_counts.get("admiral", 0)
        else:
            initial_admiral_mail = 0
        deadline = time.monotonic() + timeout_secs

        while True:
            try:
                r = self.call_gateway(crew, crew_id, "GET", "/api/spawn")
            except CrewUnresponsiveError as e:
                return {"error": str(e), "crew_id": crew_id}
            agents = r.get("agents", [])

            # Check if any task is done
            any_done = any(a.get("done", False) for a in agents)

            # Single exec reads all mailboxes at once; split into persona summary
            # and admiral count for the response surface.
            mail_counts = self.read_mail_counts(podman, container)
            mail_subjects = self.read_mail_subjects(podman, container)
            mail_summary: dict[str, int] = {
                name: mail_counts[name]
                for name in PERSONA_NAMES
                if mail_counts.get(name, 0) > 0
            }
            admiral_mail = mail_counts.get("admiral", 0)

            # Snapshot the timestamp entries for the listed agents under the lock,
            # then build the response list from the snapshot so the comprehension
            # does not read self._task_timestamps concurrently with writes.
            with self._task_timestamps_lock:
                self._expire_completed(datetime.now(timezone.utc))
                _ts_snapshot = {
                    a.get("id", ""): dict(self._task_timestamps.get(a.get("id", ""), {}))
                    for a in agents
                }

            task_list = [
                {
                    "task_id": a.get("id"),
                    "crew_id": crew_id,
                    "task": a.get("task", "")[:80],
                    "agent": a.get("agent", ""),
                    "done": a.get("done", False),
                    "elapsed_secs": int(a.get("elapsed", 0)),
                    "last_tool": a.get("last_tool", ""),
                    "outcome": a.get("outcome", ""),
                    "error": a.get("error", ""),
                    # Include per-task timestamps (null if missing)
                    "created_at": _ts_snapshot.get(a.get("id", ""), {}).get("created_at"),
                    "started_at": _ts_snapshot.get(a.get("id", ""), {}).get("started_at"),
                    "completed_at": _ts_snapshot.get(a.get("id", ""), {}).get("completed_at"),
                }
                for a in agents
            ]
            # List view: explain sign-in failures from the recorded state only,
            # never probing the crew once per listed task.
            for entry in task_list:
                if entry["done"] and entry["error"]:
                    explained = self.sign_in().explain_failure(
                        crew_id, crew, entry["error"], probe=False,
                    )
                    if explained:
                        entry.update(explained)

            # Build subject summaries for all persona mailboxes + captain + admiral.
            # captain/admiral come from the single self.read_mail_subjects exec above.
            subjects_summary: dict[str, list[str]] = {}
            for name in PERSONA_NAMES:
                subs = mail_subjects.get(name, [])
                if subs:
                    subjects_summary[f"{name}_subjects"] = subs
            captain_subjects = mail_subjects.get("captain", [])
            admiral_subjects = mail_subjects.get("admiral", [])
            subjects_summary["captain_subjects"] = captain_subjects
            subjects_summary["captain_mail"] = len(captain_subjects)
            subjects_summary["admiral_subjects"] = admiral_subjects
            subjects_summary["admiral_mail"] = len(admiral_subjects)

            out: dict[str, Any] = {
                "crew_id": crew_id,
                "tasks": task_list,
                "mail_summary": mail_summary,
                "agent_subjects": mail_subjects,
                **subjects_summary,
            }

            if any_done or timeout_secs == 0:
                return out

            # Check for admiral mail early-return
            if admiral_mail > initial_admiral_mail:
                out["reason"] = "admiral_mail"
                return out

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                out["reason"] = "timeout"
                return out

            # F-03: same as self._pickup_single — time.sleep is safe in executor thread.
            time.sleep(min(3, remaining))
