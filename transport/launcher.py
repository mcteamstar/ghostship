"""CrewLauncher — owns the per-crew concurrency state and launch logic.

The CrewLauncher class centralises the state that was previously spread across
lifecycle.py module-level globals (_startup_events, _crew_restart_outcomes,
_startup_generation, _recovery_locks, _warm_markers). By moving this state into
a single class instance, it becomes possible to test the launch logic in
isolation and to inject different implementations.

TRN-240 task 6.1: skeleton only — instance attributes and helper methods with
no business logic yet. Logic migrates in tasks 6.2-6.4.

Design notes (design.md):
- D3: module-level singleton ``_launcher`` is initialised at the bottom of this
  file so that lifecycle.py (which imports from launcher.py) sees a single
  shared instance.
- D4: ``_NUKED_DURING_RESTART`` sentinel is a module-level object imported from
  lifecycle.py to maintain identity with existing callers that compare
  ``is _NUKED_DURING_RESTART``.
"""

from __future__ import annotations

import threading
from typing import Any

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
