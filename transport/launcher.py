"""CrewLauncher — owns the per-crew concurrency state and launch logic.

The CrewLauncher class centralises the state that was previously spread across
lifecycle.py module-level globals (_startup_events, _crew_restart_outcomes,
_startup_generation, _recovery_locks, _warm_markers). By moving this state into
a single class instance, it becomes possible to test the launch logic in
isolation and to inject different implementations.

TRN-240 task 6.1: skeleton only — instance attributes and helper methods with
no business logic yet. Logic migrates in tasks 6.2-6.4.

TRN-240 task 6.2: implement CrewLauncher.ensure_running, porting
lifecycle._ensure_crew_running with concurrency state moved to self.*.

Design notes (design.md):
- D3: module-level singleton ``_launcher`` is initialised at the bottom of this
  file so that lifecycle.py (which imports from launcher.py) sees a single
  shared instance.
- D4: ``_NUKED_DURING_RESTART`` sentinel is a module-level object imported from
  lifecycle.py to maintain identity with existing callers that compare
  ``is _NUKED_DURING_RESTART``.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

try:
    from config import Config  # container: flat /app/
except ImportError:
    from transport.config import Config  # local dev

try:
    from registry import CrewRegistry, registry  # container: flat /app/
except ModuleNotFoundError:
    from transport.registry import CrewRegistry, registry  # local dev

try:
    from podman import PodmanClient, _get_podman  # container: flat /app/
except ModuleNotFoundError:
    from transport.podman import PodmanClient, _get_podman  # local dev

# _NUKED_DURING_RESTART is defined in lifecycle.py and is the sentinel returned
# by _ensure_crew_running when a concurrent nuke() removes the crew between
# container_start and post-start setup.  We import it here to maintain identity
# (existing callers compare ``is _NUKED_DURING_RESTART``, not equality).  This
# is a deliberate circular-safe import — launcher.py is not imported by
# lifecycle.py at module level; lifecycle.py imports launcher lazily or not at
# all until tasks 6.2-6.4 complete the migration.
try:
    from lifecycle import _NUKED_DURING_RESTART  # container: flat /app/
except ModuleNotFoundError:
    from transport.lifecycle import _NUKED_DURING_RESTART  # local dev


class CrewLauncher:
    """Owns the per-crew concurrency state and crew launch logic.

    Instance attributes mirror the lifecycle.py module-level globals that will
    migrate here across tasks 6.2-6.4:

    ``_startup_events``         — per-crew threading.Event (serialises restarts)
    ``_startup_events_lock``    — guards _startup_events + _crew_restart_outcomes
    ``_crew_restart_outcomes``  — per-crew (success, exc) recorded by the leader
    ``_startup_generation``     — restart cycle generation counter per crew
    ``_recovery_locks``         — per-crew non-reentrant recovery lock
    ``_recovery_locks_lock``    — guards _recovery_locks
    ``_warm_markers``           — per-crew ACP prewarm marker (monotonic ts)
    ``_warm_markers_lock``      — guards _warm_markers
    """

    def __init__(
        self,
        registry: CrewRegistry,
        podman: PodmanClient,
        cfg: Config,
    ) -> None:
        self._registry = registry
        self._podman = podman
        self._cfg = cfg

        # ── Per-crew startup serialisation ────────────────────────────────────
        self._startup_events: dict[str, threading.Event] = {}
        self._startup_events_lock = threading.Lock()
        self._crew_restart_outcomes: dict[str, tuple[bool, Exception | None]] = {}
        self._startup_generation: dict[str, int] = {}

        # ── Per-crew recovery lock ─────────────────────────────────────────────
        self._recovery_locks: dict[str, threading.Lock] = {}
        self._recovery_locks_lock = threading.Lock()

        # ── ACP warm markers ──────────────────────────────────────────────────
        self._warm_markers: dict[str, float] = {}
        self._warm_markers_lock = threading.Lock()

    def get_ensure_running_lock(self, crew_id: str) -> threading.Lock:
        """Return or create a per-crew lock for serialising recovery attempts.

        Mirrors the module-level ``_get_recovery_lock(crew_id)`` helper in
        lifecycle.py. Returns a plain (non-reentrant) threading.Lock — callers
        must not call ``ensure_running`` while holding it (D1).
        """
        with self._recovery_locks_lock:
            return self._recovery_locks.setdefault(crew_id, threading.Lock())

    def get_startup_event(self, crew_id: str) -> threading.Event | None:
        """Return the in-progress startup Event for *crew_id*, or None."""
        return self._startup_events.get(crew_id)

    # ── Active-limit and memory-gate helpers ─────────────────────────────────

    def _check_active_limit(self, podman: "PodmanClient", crew_id: str) -> None:
        """Raise RuntimeError if the active-crew limit is reached.

        Counts only crews whose container is actually running in Podman (not
        merely those the registry marks "running"). A stale "running" entry
        (container stopped externally) does not count toward the limit.

        No-op when GA_MAX_ACTIVE_CREWS == 0 (disabled).
        """
        try:
            from lifecycle import GA_MAX_ACTIVE_CREWS  # container
        except ModuleNotFoundError:
            from transport.lifecycle import GA_MAX_ACTIVE_CREWS  # local dev

        if GA_MAX_ACTIVE_CREWS <= 0:
            return

        with registry:
            running_snapshot = [
                (cid, entry.get("container"))
                for cid, entry in registry._reg["crews"].items()
                if entry.get("status") == "running"
            ]

        active = 0
        corrections: list[str] = []
        for cid, container in running_snapshot:
            if not container:
                corrections.append(cid)
                continue
            try:
                if podman.container_is_running(container):
                    active += 1
                else:
                    corrections.append(cid)
            except Exception as e:
                # Transient Podman error — do NOT mark as stopped; the
                # container state is unknown and we must not remove it from
                # the running count or mark it stopped on an ambiguous error.
                logger.warning(
                    "Active-limit check: transient Podman error for crew %s "
                    "— skipping correction: %s", cid, e,
                )
                active += 1  # assume still running to avoid under-counting

        if corrections:
            with registry:
                for cid in corrections:
                    entry = registry._reg["crews"].get(cid)
                    if entry is not None and entry.get("status") == "running":
                        entry["status"] = "stopped"
            logger.info(
                "Active-limit check corrected %d stale running entr%s to stopped: %s",
                len(corrections),
                "y" if len(corrections) == 1 else "ies",
                ", ".join(corrections),
            )

        if active >= GA_MAX_ACTIVE_CREWS:
            raise RuntimeError(
                f"Active crew limit ({GA_MAX_ACTIVE_CREWS}) reached — "
                "wait for a running crew to idle out or nuke one first"
            )

    def _check_memory_gate(self, podman: "PodmanClient", crew_id: str) -> None:
        """Raise RuntimeError if available memory is below the required minimum.

        No-op when GA_MIN_FREE_MEM_GB == 0 (disabled).
        """
        try:
            from lifecycle import GA_MIN_FREE_MEM_GB, _wait_for_memory  # container
        except ModuleNotFoundError:
            from transport.lifecycle import GA_MIN_FREE_MEM_GB, _wait_for_memory  # local dev

        if GA_MIN_FREE_MEM_GB <= 0:
            return

        free_gb = _wait_for_memory(podman, GA_MIN_FREE_MEM_GB, 60)
        if free_gb < GA_MIN_FREE_MEM_GB:
            raise RuntimeError(
                f"Insufficient available memory to start crew {crew_id}: "
                f"{free_gb}GB free, {GA_MIN_FREE_MEM_GB}GB required. "
                f"Retry in a moment."
            )

    # ── ensure_running ────────────────────────────────────────────────────────

    def ensure_running(
        self,
        crew,
        crew_id: str,
        *,
        touch: bool = True,
    ):
        """Ensure a crew container is running, starting it if stopped.

        Uses a per-crew Event to serialise concurrent restart attempts — the
        first caller does the work, subsequent callers wait for it to finish
        then read the refreshed crew dict from the registry.

        The ``touch`` flag controls whether a successful call refreshes the
        crew activity timestamp.

        Returns an updated crew dict (cookie may be refreshed), or the
        ``_NUKED_DURING_RESTART`` sentinel if the crew was concurrently nuked.
        """
        try:
            from lifecycle import (  # container
                _get_podman,
                _to_crew,
                _probe_gateway,
                _get_crew,
                _wait_gateway,
                _mint_cookie,
                _mint_internal_cookie,
                _patch_crew_config,
                _deployed_agent_names,
                _enroll_crew_members,
                _write_dashboard_cookie,
            )
            from registry import _touch_crew  # container
        except ModuleNotFoundError:
            from transport.lifecycle import (  # local dev
                _get_podman,
                _to_crew,
                _probe_gateway,
                _get_crew,
                _wait_gateway,
                _mint_cookie,
                _mint_internal_cookie,
                _patch_crew_config,
                _deployed_agent_names,
                _enroll_crew_members,
                _write_dashboard_cookie,
            )
            from transport.registry import _touch_crew  # local dev

        try:
            podman = _get_podman()
        except Exception as e:
            raise RuntimeError(str(e))

        c = _to_crew(crew_id, crew)

        # D5: Check for an in-progress restart BEFORE probing/stopping the
        # container. If a concurrent leader is already restarting this crew,
        # go straight to the waiter path — probing or stopping the container
        # mid-restart is wrong.
        with self._startup_events_lock:
            _early_in_progress = crew_id in self._startup_events

        if not _early_in_progress:
            if podman.container_is_running(c.container):
                # Gateway liveness probe: a running container may have a dead
                # gateway
                if _probe_gateway(c.gateway_url()):
                    if touch:
                        _touch_crew(crew_id)
                    return crew
                # Gateway is dead inside a running container — fall through to
                # restart
                logger.info(
                    "Crew %s container running but gateway probe failed — "
                    "restarting", crew_id,
                )
                podman.container_stop(c.container)

        # Serialise concurrent restarts for this crew
        with self._startup_events_lock:
            if crew_id in self._startup_events:
                event = self._startup_events[crew_id]
                is_leader = False
                # Capture generation before releasing lock
                _waiter_gen = self._startup_generation.get(crew_id, 0)
            else:
                event = threading.Event()
                self._startup_events[crew_id] = event
                is_leader = True
                # Drop any outcome left by a PRIOR leader for this crew. The
                # outcome map is never popped on completion (its read happens
                # after event.set(), so it cannot be cleared in the leader's
                # finally without racing the waiter), so a stale entry survives
                # between cycles. If we did not clear it, a waiter whose
                # event.wait() times out would read the previous cycle's failure
                # and raise an unrelated exception. Clearing at election makes
                # the map hold at most one entry per crew AND guarantees a
                # timed-out waiter sees None (→ explicit timeout error) rather
                # than a stale outcome.
                self._crew_restart_outcomes.pop(crew_id, None)
                # Increment generation for this new restart cycle
                self._startup_generation[crew_id] = (
                    self._startup_generation.get(crew_id, 0) + 1
                )
                _waiter_gen = self._startup_generation[crew_id]

        if not is_leader:
            # Another caller is already restarting — wait for it then return
            # the refreshed crew dict
            logger.info("Crew %s restart already in progress — waiting", crew_id)
            event.wait(timeout=45)
            # Read the outcome the leader recorded before firing the Event.
            with self._startup_events_lock:
                outcome = self._crew_restart_outcomes.get(crew_id)
                _current_gen = self._startup_generation.get(crew_id, 0)
            if _current_gen != _waiter_gen:
                raise RuntimeError(
                    f"Crew {crew_id} restart (concurrent) failed -- restart "
                    f"cycle changed during wait (waited on gen {_waiter_gen}, "
                    f"current gen {_current_gen}); a new restart cycle started "
                    f"before outcome was read"
                )
            if outcome is None:
                raise RuntimeError(
                    f"Crew {crew_id} restart (concurrent) failed -- leader did "
                    f"not record an outcome within the wait window"
                )
            success, exc = outcome
            if not success:
                raise exc if exc is not None else RuntimeError(
                    f"Crew {crew_id} restart (concurrent) failed"
                )
            # TRN-238 QA-2 (waiter path): the leader may have returned
            # _NUKED_DURING_RESTART — a concurrent nuke() removed the crew
            # between container_start and post-start setup.
            try:
                crew_after = _get_crew(crew_id)
            except KeyError:
                logger.info(
                    "Crew %s was nuked during restart (registry entry gone "
                    "after waiter woke) — returning _NUKED_DURING_RESTART "
                    "sentinel", crew_id,
                )
                return _NUKED_DURING_RESTART
            crew_after_obj = _to_crew(crew_id, crew_after)
            if crew_after_obj.status in ("stopped", "launching", None):
                raise RuntimeError(
                    f"Crew {crew_id} restart (concurrent) failed -- status is "
                    f"still {crew_after_obj.status!r}"
                )
            return crew_after

        # We are the leader — do the restart
        _outcome: tuple[bool, Exception | None] = (
            False,
            RuntimeError(f"Crew {crew_id} restart (leader) failed"),
        )
        try:
            logger.info("Crew %s is stopped — restarting", crew_id)

            self._check_active_limit(podman, crew_id)
            self._check_memory_gate(podman, crew_id)

            podman.container_start(c.container)
            crew_url = c.gateway_url()

            # TRN-238 QA-2: a concurrent nuke() can remove this crew's registry
            # entry between the container_start above and the post-start setup
            # below.
            with registry:
                crew_still_registered = crew_id in registry._reg["crews"]
            if not crew_still_registered:
                logger.info(
                    "Crew %s was nuked during restart (registry entry gone "
                    "after container_start) — aborting post-start setup",
                    crew_id,
                )
                _outcome = (True, None)
                return _NUKED_DURING_RESTART

            _patch_crew_config(podman, c.container)
            podman.container_stop(c.container)
            podman.container_start(c.container)
            if not _wait_gateway(crew_url, timeout=60):
                raise RuntimeError(
                    f"Gateway did not recover after config re-patch for crew "
                    f"{crew_id}"
                )

            # Refresh cookie (old one may have expired)
            new_cookie = _mint_cookie(podman, c.container, crew_url)
            if new_cookie:
                try:
                    with registry:
                        if crew_id in registry._reg["crews"]:
                            registry._reg["crews"][crew_id]["cookie"] = new_cookie
                            registry._reg["crews"][crew_id]["status"] = "running"
                            registry._reg["crews"][crew_id]["last_used"] = time.time()
                except Exception as reg_exc:
                    # D7b: the container is running but we could not persist the
                    # "running" status. Stop the container so its real state
                    # matches the stale registry entry, then re-raise.
                    logger.error(
                        "Crew %s: registry write failed after restart (%s) — "
                        "stopping container to match registry state",
                        crew_id, reg_exc,
                    )
                    try:
                        podman.container_stop(c.container)
                    except Exception as stop_exc:
                        logger.error(
                            "Crew %s: container_stop during registry-failure "
                            "cleanup also failed: %s", crew_id, stop_exc,
                        )
                    raise
                c.cookie = new_cookie
                crew = (
                    {**crew, "cookie": new_cookie}
                    if isinstance(crew, dict)
                    else c
                )
                logger.info("Crew %s restarted and cookie refreshed", crew_id)
                # Also refresh the internally-bound cookie for crew member
                # spawn auth
                new_internal = _mint_internal_cookie(podman, c.container)
                if new_internal:
                    with registry:
                        if crew_id in registry._reg["crews"]:
                            registry._reg["crews"][crew_id][
                                "internal_cookie"
                            ] = new_internal
                    c.internal_cookie = new_internal
                    crew = (
                        {**crew, "internal_cookie": new_internal}
                        if isinstance(crew, dict)
                        else c
                    )
                    _write_dashboard_cookie(podman, c.container, new_internal)
                else:
                    logger.warning(
                        "Crew %s restarted but internal cookie refresh failed",
                        crew_id,
                    )
            else:
                logger.warning(
                    "Crew %s restarted but cookie refresh failed", crew_id
                )
            deployed = _deployed_agent_names(podman, c.container)
            _enroll_crew_members(crew, crew_id, deployed)
            with registry:
                if crew_id in registry._reg["crews"]:
                    registry._reg["crews"][crew_id]["enrolled_agents"] = [
                        n.removesuffix(".json") for n in deployed
                    ]
            _touch_crew(crew_id)
            _outcome = (True, None)
            return crew
        except Exception as exc:
            _outcome = (False, exc)
            raise
        finally:
            # Always unblock waiters and clean up, even on error. Publish the
            # outcome BEFORE firing the Event so a waiter that wakes immediately
            # sees it.
            with self._startup_events_lock:
                self._crew_restart_outcomes[crew_id] = _outcome
                self._startup_events.pop(crew_id, None)
            event.set()

    # ── finish_setup ──────────────────────────────────────────────────────────

    def finish_setup(
        self,
        podman,
        crew_id: str,
        container: str,
        volume: str,
        home_volume: str,
        auth_b64: str,
        composition: str = "spec-ops",
        composition_entry: dict | None = None,
        *,
        admiral_secret: str,
        dashboard: bool = False,
    ) -> dict:
        """Complete crew setup after auth is confirmed.

        Ports ``lifecycle._finish_crew_setup``: copy agents/skills/steering,
        patch config, mint cookie, write registry entry, enroll members, prewarm.

        Returns a result dict on success; ``{"error": ...}`` on failure.
        """
        try:
            from lifecycle import (  # container
                GA_CREW_ACP_BACKEND,
                CREW_GATEWAY_PORT,
                ANTHROPIC_BASE_URL,
                ANTHROPIC_API_KEY,
                CLAUDE_CODE_OAUTH_TOKEN,
                OPENAI_BASE_URL,
                OPENAI_API_KEY,
                KIRO_API_KEY,
                KIRO_AGENTS_DIR,
                SCRIPTS_DIR,
                _wait_gateway,
                _cleanup_crew,
                _inject_auth,
                _inject_claude_auth,
                _inject_codex_auth,
                _claude_auth_exists,
                _codex_auth_exists,
                _patch_crew_config,
                _seed_openspec_store,
                _inject_policy,
                _patch_models,
                _mint_cookie,
                _mint_internal_cookie,
                _write_dashboard_cookie,
                _enroll_crew_members,
                _prewarm_crew,
                _secret_identifier,
            )
            from academy import AcademyLoader  # container
        except ModuleNotFoundError:
            from transport.lifecycle import (  # local dev
                GA_CREW_ACP_BACKEND,
                CREW_GATEWAY_PORT,
                ANTHROPIC_BASE_URL,
                ANTHROPIC_API_KEY,
                CLAUDE_CODE_OAUTH_TOKEN,
                OPENAI_BASE_URL,
                OPENAI_API_KEY,
                KIRO_API_KEY,
                KIRO_AGENTS_DIR,
                SCRIPTS_DIR,
                _wait_gateway,
                _cleanup_crew,
                _inject_auth,
                _inject_claude_auth,
                _inject_codex_auth,
                _claude_auth_exists,
                _codex_auth_exists,
                _patch_crew_config,
                _seed_openspec_store,
                _inject_policy,
                _patch_models,
                _mint_cookie,
                _mint_internal_cookie,
                _write_dashboard_cookie,
                _enroll_crew_members,
                _prewarm_crew,
                _secret_identifier,
            )
            from transport.academy import AcademyLoader  # local dev

        try:
            from crew import Crew  # container
            from datetime import datetime, timezone  # always available
        except ModuleNotFoundError:
            from transport.crew import Crew
            from datetime import datetime, timezone

        crew_url = f"http://{container}:{CREW_GATEWAY_PORT}"

        # depends on: container running (pre-restart)
        if not _wait_gateway(crew_url, timeout=10):
            podman.container_stop(container)
            podman.container_start(container)
            if not _wait_gateway(crew_url, timeout=60):
                _cleanup_crew(podman, container, volume, home_volume)
                return {"error": f"Gateway did not recover for crew {crew_id}"}

        # Auth injection (backend-specific)
        if GA_CREW_ACP_BACKEND == "claude":
            _effective_endpoint = ANTHROPIC_BASE_URL or "api.anthropic.com"
            logger.warning(
                "GA_CREW_ACP_BACKEND=claude: crew %s requires outbound access to "
                "%s to function", crew_id, _effective_endpoint,
            )
            if (not ANTHROPIC_API_KEY and not CLAUDE_CODE_OAUTH_TOKEN
                    and _claude_auth_exists()):
                try:
                    _inject_claude_auth(podman, container)
                except Exception as e:
                    logger.warning(
                        "Claude OAuth auth injection failed for crew %s: %s — "
                        "crew may be unable to authenticate against "
                        "api.anthropic.com", crew_id, e,
                    )
        elif GA_CREW_ACP_BACKEND == "codex":
            _effective_endpoint = OPENAI_BASE_URL or "api.openai.com"
            logger.warning(
                "GA_CREW_ACP_BACKEND=codex: crew %s requires outbound access to "
                "%s to function", crew_id, _effective_endpoint,
            )
            if not OPENAI_API_KEY and _codex_auth_exists():
                try:
                    _inject_codex_auth(podman, container)
                except Exception as e:
                    logger.warning(
                        "Codex OAuth auth injection failed for crew %s: %s — "
                        "crew may be unable to authenticate against "
                        "api.openai.com", crew_id, e,
                    )
        else:
            # kiro path
            if not KIRO_API_KEY:
                _inject_auth(podman, container, auth_b64)

        policy_signing_key = __import__("secrets").token_hex(32)

        _patch_crew_config(podman, container, composition_entry)

        podman.container_stop(container)
        podman.container_start(container)
        if not _wait_gateway(crew_url, timeout=60):
            _cleanup_crew(podman, container, volume, home_volume)
            return {
                "error": f"Gateway did not recover after auth restart for crew {crew_id}"
            }

        # Copy agents/skills/steering via AcademyLoader
        _loader = AcademyLoader(podman, container, composition_entry)
        _loader_result = _loader.copy_all()
        copied_agents = _loader_result["agents"]

        _seed_openspec_store(podman, container)

        policy_version = None
        policy_warning: str | None = None
        try:
            policy_version = _inject_policy(
                podman, container, composition, policy_signing_key
            )
        except Exception as e:
            policy_warning = str(e)
            logger.error(
                "Policy injection failed for %s: %s — continuing without policy",
                container, e,
            )

        for _ in range(20):
            check = podman.container_exec(container, [
                "python3", f"{SCRIPTS_DIR}/check_gateway_ready.py", KIRO_AGENTS_DIR,
            ])
            if "ready" in check:
                break
            time.sleep(0.5)

        _patch_models(podman, container)

        cookie = _mint_cookie(podman, container, crew_url)
        if not cookie:
            _cleanup_crew(podman, container, volume, home_volume)
            return {"error": f"Failed to mint session cookie for crew {crew_id}"}

        internal_cookie = _mint_internal_cookie(podman, container)
        if internal_cookie:
            _write_dashboard_cookie(podman, container, internal_cookie)
        else:
            logger.warning(
                "Could not mint internal cookie for crew %s — spawn auth unavailable",
                crew_id,
            )

        crew_image_version = "unknown"
        try:
            inspect_data = podman.container_inspect(container)
            labels = inspect_data.get("Config", {}).get("Labels", {})
            crew_image_version = labels.get("org.ghostship.version", "unknown")
        except Exception as e:
            logger.warning("Could not read version label from %s: %s", container, e)

        # Build the Crew object and write it to the registry
        crew_obj = Crew(
            crew_id=crew_id,
            container=container,
            volume=volume,
            home_volume=home_volume,
            port=5476,
            cookie=cookie,
            internal_cookie=internal_cookie or "",
            status="running",
            composition=composition,
            acp_backend=GA_CREW_ACP_BACKEND,
            created_at=datetime.now(timezone.utc).isoformat(),
            last_used=time.time(),
            enrolled_agents=[n.removesuffix(".json") for n in copied_agents],
            admiral_secret_id=_secret_identifier(admiral_secret),
            crew_image_version=crew_image_version,
        )
        if policy_version is not None:
            crew_obj.policy_version = policy_version
            crew_obj.policy_signing_key_id = _secret_identifier(policy_signing_key)

        with registry:
            registry.put(crew_obj)

        # Also build the crew_entry dict for callers that expect it
        crew_entry = crew_obj.to_dict()
        if internal_cookie:
            crew_entry["internal_cookie"] = internal_cookie
        if policy_version is not None:
            crew_entry["policy_version"] = policy_version
            crew_entry["policy_signing_key_id"] = _secret_identifier(policy_signing_key)

        _enroll_crew_members(crew_entry, crew_id, copied_agents)
        logger.info("Crew %s ready", crew_id)
        result = {
            "crew_id": crew_id,
            "container": container,
            "gateway_url": crew_url,
            "status": "ready",
        }
        if policy_version is not None:
            result["policy_version"] = policy_version
        if policy_warning is not None:
            result["policy_warning"] = (
                f"Policy injection failed — crew is ungoverned: {policy_warning}"
            )

        # ACP prewarm — fire-and-report, non-fatal
        try:
            pw = _prewarm_crew(crew_entry, crew_id)
            if pw.get("pre_warm_task_id"):
                result["pre_warm_task_id"] = pw["pre_warm_task_id"]
            result["pre_warm_status"] = pw.get("status", "unknown")
        except Exception as exc:
            logger.warning("Crew %s prewarm failed (non-fatal): %s", crew_id, exc)
            result["pre_warm_status"] = "error"

        return result

    # ── _run_restart_cycle ────────────────────────────────────────────────────

    def _run_restart_cycle(self, crew, crew_id: str):
        """Run the patch-config → stop → start → wait-gateway → mint-cookie cycle.

        Used by ``_reconcile_registry`` for stopped crews on startup.  Mirrors
        the restart body inside ``ensure_running``:
            patch config → stop → start → wait_gateway → mint cookie → update registry

        Returns an update-dict ``{"status": "running", ...}`` on success,
        or ``{"status": "stopped"}`` on failure (gateway timeout, exception, …).

        On success the caller is also responsible for calling
        ``_enroll_crew_members`` and ``_reseed_crew_schedules`` — those require
        the updated crew dict and are orchestration concerns outside this method.
        """
        try:
            from lifecycle import (  # container
                _get_podman,
                _to_crew,
                _patch_crew_config,
                _wait_gateway,
                _mint_cookie,
                CREW_GATEWAY_PORT,
            )
        except ModuleNotFoundError:
            from transport.lifecycle import (  # local dev
                _get_podman,
                _to_crew,
                _patch_crew_config,
                _wait_gateway,
                _mint_cookie,
                CREW_GATEWAY_PORT,
            )

        try:
            podman = _get_podman()
        except Exception as e:
            logger.warning("Reconcile restart: could not get Podman client for crew %s: %s", crew_id, e)
            return {"status": "stopped"}

        c = _to_crew(crew_id, crew)
        container = c.container
        crew_url = f"http://{container}:{CREW_GATEWAY_PORT}"

        try:
            podman.container_start(container)
            _patch_crew_config(podman, container)
            podman.container_stop(container)
            podman.container_start(container)
            if _wait_gateway(crew_url, timeout=60):
                new_cookie = _mint_cookie(podman, container, crew_url)
                update = {
                    "status": "running",
                    "last_used": time.time(),
                    **({} if not new_cookie else {"cookie": new_cookie}),
                }
                return update
            else:
                logger.warning(
                    "Crew %s gateway not ready after restart — leaving stopped",
                    crew_id,
                )
                return {"status": "stopped"}
        except Exception as e:
            logger.warning("Could not restart crew %s: %s", crew_id, e)
            return {"status": "stopped"}


# ── Module-level singleton ────────────────────────────────────────────────────
# Initialised after the class definition so that it is available to lifecycle.py
# and server.py at import time once those modules migrate to use it (tasks 6.2-6.4).
# The singleton uses the module-level ``registry`` singleton and the global
# ``_get_podman()`` / ``Config.from_env()`` so it is fully configured at startup.
cfg = Config.from_env()
try:
    _podman_client = _get_podman()
except Exception:
    # Podman may not be available at import time (e.g. in unit tests without the
    # Podman socket). The singleton is still created with a dummy client; the
    # real client is resolved lazily at the call sites in ensure_running / finish_setup.
    _podman_client = None  # type: ignore[assignment]

_launcher = CrewLauncher(registry=registry, podman=_podman_client, cfg=cfg)
