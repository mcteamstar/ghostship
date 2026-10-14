"""Registry — owns crews.json persistence and all CRUD on crew/schedule entries.

All reads and writes to the registry file go through this module.
Nothing outside registry.py writes the registry file directly.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from types import TracebackType
from typing import Any

try:
    from config import Config  # container: flat /app/
except ImportError:
    from transport.config import Config

try:
    from crew import Crew  # container: flat /app/
except ModuleNotFoundError:
    from transport.crew import Crew  # local dev

cfg = Config.from_env()

DATA_DIR = Path("/data")
REGISTRY_PATH = DATA_DIR / "crews.json"

logger = logging.getLogger(__name__)

# float("inf") is non-finite and raises ValueError in json.dumps; this value
# (≈ year 2286 Unix timestamp) is finite, JSON-serialisable, and practically
# unreachable as a real schedule time.
_NEVER_FIRE_AT: float = 9_999_999_999.0

_registry_lock = threading.Lock()


def _write_secret_file(path: Path, data: bytes | str) -> None:
    """Atomically write *data* to *path* with mode 0600.

    Performs the full secret-write pattern used across the transport layer:
    ``os.open`` with ``O_WRONLY|O_CREAT|O_TRUNC`` at 0o600, ``fchmod`` to
    guarantee the mode even if the file pre-existed, ``fdopen`` + write +
    ``flush`` + ``fsync`` of the file, a defensive ``os.chmod`` on the path,
    and finally an ``fsync`` of the parent directory so the file's metadata
    is durable. The parent directory is created if absent.

    Accepts ``bytes`` or ``str``; a ``str`` is encoded as UTF-8.
    """
    if isinstance(data, str):
        payload = data.encode("utf-8")
    else:
        payload = data
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        f = os.fdopen(fd, "wb")
        fd = -1
        with f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
    finally:
        if fd != -1:
            os.close(fd)
    os.chmod(path, 0o600)
    dir_fd = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


class RegistryCorruptError(RuntimeError):
    """Raised when the registry file exists but cannot be parsed as JSON.

    Gives callers (notably the MCP tool handlers in transport/server.py) a
    single named exception to catch at the tool boundary, rather than leaking
    the internal ``json.JSONDecodeError`` parsing detail. The corrupt file is
    quarantined as ``crews.json.corrupt`` before this is raised.
    """


def _load_registry() -> dict:
    try:
        if REGISTRY_PATH.exists():
            return json.loads(REGISTRY_PATH.read_text())
    except json.JSONDecodeError as e:
        logger.error("Registry file is corrupt and cannot be parsed: %s", e)
        # Append ".corrupt" rather than with_suffix(), which would REPLACE the
        # ".json" suffix and produce "crews.corrupt". The spec mandates the
        # quarantine file be named "crews.json.corrupt".
        corrupt = REGISTRY_PATH.with_name(REGISTRY_PATH.name + ".corrupt")
        os.replace(REGISTRY_PATH, corrupt)
        # Raise a named exception rather than re-raising the internal
        # json.JSONDecodeError, so MCP tool handlers catch one thing.
        raise RegistryCorruptError(
            "registry corrupt — crews.json.corrupt preserved for inspection"
        ) from e
    except Exception as e:
        # Re-raise so callers can decide: returning an empty dict here caused
        # a subsequent _save_registry call to silently clobber every crew.
        # Background-thread callers (monitors, lifecycle) must catch explicitly
        # and fail-open; MCP tool handlers let this propagate to the boundary.
        logger.error("Failed to load registry: %s", e)
        raise
    return {"crews": {}}


def _save_registry(reg: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = REGISTRY_PATH.with_suffix(".tmp")
    # Write the serialised registry to the temp file using the shared atomic
    # 0600 write pattern, then atomically rename it into place. The rename and
    # the post-rename durability steps (chmod + directory fsync) are kept here
    # because they are specific to the temp-file swap _save_registry performs.
    _write_secret_file(tmp, json.dumps(reg, indent=2))
    os.replace(tmp, REGISTRY_PATH)
    os.chmod(REGISTRY_PATH, 0o600)
    dir_fd = os.open(str(REGISTRY_PATH.parent), os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


# ── Schedule registry helpers ─────────────────────────────────────────────────

def _get_crew_schedules(reg: dict, crew_id: str) -> list:
    """Return the schedules list for a crew, defaulting to []."""
    crew_entry = reg.get("crews", {}).get(crew_id, {})
    return crew_entry.get("schedules", [])


def _upsert_crew_schedule(reg: dict, crew_id: str, job: dict) -> None:
    """Insert or update a schedule entry by job_id (or type for captain entries)."""
    crew_entry = reg.get("crews", {}).get(crew_id)
    if crew_entry is None:
        return
    schedules = crew_entry.setdefault("schedules", [])
    # Captain entries are matched by type, not job_id (they have no gateway job_id)
    if job.get("type") == "captain":
        for i, existing in enumerate(schedules):
            if existing.get("type") == "captain":
                schedules[i] = job
                return
        schedules.append(job)
        return
    job_id = job.get("job_id")
    for i, existing in enumerate(schedules):
        if existing.get("job_id") == job_id:
            schedules[i] = job
            return
    schedules.append(job)


def _remove_crew_schedule(reg: dict, crew_id: str, job_id: str) -> None:
    """Remove a schedule entry by job_id."""
    crew_entry = reg.get("crews", {}).get(crew_id)
    if crew_entry is None:
        return
    schedules = crew_entry.get("schedules", [])
    crew_entry["schedules"] = [s for s in schedules if s.get("job_id") != job_id]


def _advance_next_fire_at(job: dict) -> None:
    """Mutate next_fire_at based on interval_secs or next cron tick."""
    if job.get("one_shot"):
        # One-shot job (delay-based): mark as fired by setting far future.
        job["next_fire_at"] = _NEVER_FIRE_AT
        return
    interval = job.get("interval_secs")
    if interval:
        job["next_fire_at"] = time.time() + interval
    elif job.get("cron_expr"):
        # Compute true next fire time using croniter.  Fall back to +60s for
        # malformed expressions (same cadence as before, but now only for
        # genuinely invalid cron strings).
        from croniter import croniter as _croniter
        try:
            job["next_fire_at"] = _croniter(job["cron_expr"], time.time()).get_next(float)
        except Exception as _cron_err:
            logger.warning(
                "croniter failed for cron_expr %r, falling back to +60s: %s",
                job.get("cron_expr"), _cron_err,
            )
            job["next_fire_at"] = time.time() + 60
    else:
        # Unknown schedule type: mark as fired to avoid infinite re-fire.
        job["next_fire_at"] = _NEVER_FIRE_AT


def _get_crew(crew_id: str) -> dict:
    with _registry_lock:
        reg = _load_registry()
    crew = reg["crews"].get(crew_id)
    if not crew:
        raise KeyError(
            f"Crew '{crew_id}' not found. "
            f"Use launch to create it first."
        )
    return crew


def _touch_crew(crew_id: str) -> None:
    """Update last_used timestamp for a crew."""
    with _registry_lock:
        reg = _load_registry()
        if crew_id in reg["crews"]:
            reg["crews"][crew_id]["last_used"] = time.time()
            _save_registry(reg)


# ── Per-crew signing-secret store ────────────────────────────────────────────
# The admiral_secret is stored in a separate file under
# DATA_DIR/secrets/<crew_id>.admiral_secret (mode 0600). This keeps the value
# in a file that inherits DATA_DIR's access controls (0700 for multi-operator
# deployments) while keeping it out of the structured JSON registry that is
# more likely to be backed up or inspected.

_SECRETS_DIR_NAME = "secrets"


def _crew_secret_path(crew_id: str) -> Path:
    """Return the path for a crew's admiral signing-secret file."""
    return DATA_DIR / _SECRETS_DIR_NAME / f"{crew_id}.admiral_secret"


def _write_crew_secret(crew_id: str, secret: str) -> None:
    """Write the admiral signing secret for *crew_id* to an isolated file.

    The file is created with mode 0600. Parent directory is created if absent.
    This is the only place the plaintext secret is persisted to disk; it is
    never stored in crews.json.
    """
    secret_path = _crew_secret_path(crew_id)
    _write_secret_file(secret_path, secret)


def _read_crew_secret(crew_id: str) -> str | None:
    """Return the admiral signing secret for *crew_id*, or None if absent."""
    secret_path = _crew_secret_path(crew_id)
    try:
        return secret_path.read_text().strip()
    except FileNotFoundError:
        return None


def _delete_crew_secret(crew_id: str) -> None:
    """Remove the admiral signing-secret file for *crew_id* (nuke path)."""
    secret_path = _crew_secret_path(crew_id)
    try:
        secret_path.unlink()
    except FileNotFoundError:
        pass


# ── Batch registry helpers ────────────────────────────────────────────────────
# Batch dispatch records live under crews[crew_id]["batches"], co-located with
# schedule and crew metadata. Each entry records the batch_id, its constituent
# task_ids, an ISO-8601 UTC created_at, and a status (pending | partial |
# complete). All CRUD goes through _registry_lock so a batch write is atomic
# with respect to every other registry mutation.


def _write_batch(
    crew_id: str,
    batch_id: str,
    task_ids: list[str],
    status: str,
    created_at: str | None = None,
) -> dict | None:
    """Write (upsert) a batch entry under crews[crew_id]["batches"].

    Returns the stored batch dict, or None if the crew does not exist. The
    write is atomic within _registry_lock. If a batch with the same batch_id
    already exists it is replaced in place; otherwise the new entry is
    appended. ``created_at`` defaults to now (ISO-8601 UTC) when omitted.
    """
    if created_at is None:
        created_at = (
            time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "+00:00"
        )
    entry = {
        "batch_id": batch_id,
        "task_ids": list(task_ids),
        "created_at": created_at,
        "status": status,
    }
    with _registry_lock:
        reg = _load_registry()
        crew_entry = reg.get("crews", {}).get(crew_id)
        if crew_entry is None:
            return None
        batches = crew_entry.setdefault("batches", [])
        for i, existing in enumerate(batches):
            if existing.get("batch_id") == batch_id:
                batches[i] = entry
                break
        else:
            batches.append(entry)
        _save_registry(reg)
    return entry


def _get_batch(crew_id: str, batch_id: str) -> dict | None:
    """Return the batch entry dict for *batch_id*, or None if not found."""
    with _registry_lock:
        reg = _load_registry()
    crew_entry = reg.get("crews", {}).get(crew_id, {})
    for entry in crew_entry.get("batches", []):
        if entry.get("batch_id") == batch_id:
            return entry
    return None


def _update_batch_status(crew_id: str, batch_id: str, status: str) -> dict | None:
    """Update the ``status`` field of a batch entry atomically.

    Status transitions through pending -> partial -> complete. Returns the
    updated entry, or None if the crew or batch is not found.
    """
    with _registry_lock:
        reg = _load_registry()
        crew_entry = reg.get("crews", {}).get(crew_id)
        if crew_entry is None:
            return None
        for entry in crew_entry.get("batches", []):
            if entry.get("batch_id") == batch_id:
                entry["status"] = status
                _save_registry(reg)
                return entry
    return None


def _delete_batch(crew_id: str, batch_id: str) -> bool:
    """Remove a single batch entry by batch_id. Returns True if removed."""
    with _registry_lock:
        reg = _load_registry()
        crew_entry = reg.get("crews", {}).get(crew_id)
        if crew_entry is None:
            return False
        batches = crew_entry.get("batches", [])
        new_batches = [b for b in batches if b.get("batch_id") != batch_id]
        if len(new_batches) == len(batches):
            return False
        crew_entry["batches"] = new_batches
        _save_registry(reg)
    return True


def _find_batch_by_task_ids(crew_id: str, task_ids: list[str]) -> dict | None:
    """Return the first batch entry whose task_ids set contains *task_ids*, or None.

    Used by ``pickup(task_ids=[...])`` to discover the ``batch_id`` so that
    ``_update_batch_status`` can mark the batch ``complete`` when all members
    are done — satisfying the spec requirement without adding a ``batch_id``
    parameter to the ``pickup`` MCP tool surface.

    The match is a subset check: all provided *task_ids* must be members of the
    recorded batch's task list (``set(provided) <= set(recorded)``). A superset
    — more provided IDs than the batch holds — does NOT match, as that indicates
    a mis-specified call. Returns the first match found; first-match-wins is safe
    in practice because task IDs are UUIDs (collision probability negligible).
    """
    wanted = set(task_ids)
    with _registry_lock:
        reg = _load_registry()
    crew_entry = reg.get("crews", {}).get(crew_id, {})
    for entry in crew_entry.get("batches", []):
        if wanted <= set(entry.get("task_ids", [])):
            return entry
    return None


# ── CrewRegistry class ────────────────────────────────────────────────────────


class CrewRegistry:
    """Context-manager registry for crew entries.

    Usage::

        with registry:
            crew = registry.get("demo")
            if crew:
                crew.status = "running"
                registry.put(crew)

    The context manager acquires ``_registry_lock`` on entry, loads the JSON
    registry file, and releases the lock on exit.  On **clean exit**
    (``exc_type is None``) the registry is saved back to disk before the lock
    is released.  On an exceptional exit the registry is NOT saved — this
    prevents a partial write from corrupting the file.

    ``get`` / ``put`` / ``remove`` / ``list`` / ``touch`` are only valid
    inside a ``with registry:`` block (the ``_reg`` attribute is set on
    ``__enter__`` and cleared on ``__exit__``).  Calls outside a context
    block raise ``RuntimeError``.

    Design notes (TRN-240):
    - Crew objects returned by ``get``/``list`` are live references into the
      internal ``_reg`` dict — mutating them via attribute assignment and then
      calling ``put(crew)`` commits the change.
    - ``warm_until`` is in-memory only (D2) and is never persisted.
    - The lock is the same module-level ``_registry_lock`` used by the legacy
      procedural helpers, so the two APIs are mutually exclusive at the lock
      level — no deadlocks from mixing them.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._reg: dict[str, Any] | None = None

    # ── Internal load/save using self._path ──────────────────────────────────

    def _load(self) -> dict[str, Any]:
        """Load the registry from ``self._path``, returning ``{"crews": {}}`` when absent."""
        try:
            if self._path.exists():
                return json.loads(self._path.read_text())
        except json.JSONDecodeError as e:
            logger.error("CrewRegistry: registry file is corrupt: %s", e)
            corrupt = self._path.with_name(self._path.name + ".corrupt")
            os.replace(self._path, corrupt)
            raise RegistryCorruptError(
                "registry corrupt — crews.json.corrupt preserved for inspection"
            ) from e
        except Exception as e:
            logger.error("CrewRegistry: failed to load registry: %s", e)
            raise
        return {"crews": {}}

    def _save(self, reg: dict[str, Any]) -> None:
        """Save *reg* to ``self._path`` atomically (same durability guarantees as _save_registry)."""
        tmp = self._path.with_suffix(".tmp")
        _write_secret_file(tmp, json.dumps(reg, indent=2))
        os.replace(tmp, self._path)
        os.chmod(self._path, 0o600)
        dir_fd = os.open(str(self._path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> "CrewRegistry":
        _registry_lock.acquire()
        try:
            self._reg = _load_registry()
        except Exception:
            _registry_lock.release()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is None and self._reg is not None:
                _save_registry(self._reg)
        finally:
            self._reg = None
            _registry_lock.release()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _require_reg(self) -> dict[str, Any]:
        if self._reg is None:
            raise RuntimeError(
                "CrewRegistry methods must be called inside a 'with registry:' block"
            )
        return self._reg

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def get(self, crew_id: str) -> Crew | None:
        """Return the ``Crew`` for *crew_id*, or ``None`` if not found."""
        reg = self._require_reg()
        d = reg.get("crews", {}).get(crew_id)
        if d is None:
            return None
        return Crew.from_dict(crew_id, d)

    def put(self, crew: Crew) -> None:
        """Write *crew* into the registry (insert or replace by crew_id)."""
        reg = self._require_reg()
        reg.setdefault("crews", {})[crew.crew_id] = crew.to_dict()

    def remove(self, crew_id: str) -> None:
        """Remove the entry for *crew_id* (no-op if absent)."""
        reg = self._require_reg()
        reg.get("crews", {}).pop(crew_id, None)

    def list(self) -> list[Crew]:
        """Return all crews as a list of ``Crew`` objects."""
        reg = self._require_reg()
        return [
            Crew.from_dict(cid, d)
            for cid, d in reg.get("crews", {}).items()
        ]

    def touch(self, crew_id: str) -> None:
        """Update *crew_id*'s ``last_used`` timestamp to now."""
        reg = self._require_reg()
        entry = reg.get("crews", {}).get(crew_id)
        if entry is not None:
            entry["last_used"] = time.time()

    # ── Schedule methods ──────────────────────────────────────────────────────

    def get_schedules(self, crew_id: str) -> list:
        """Return the schedules list for *crew_id* (defaults to [])."""
        reg = self._require_reg()
        return _get_crew_schedules(reg, crew_id)

    def upsert_schedule(self, crew_id: str, job: dict) -> None:
        """Insert or update a schedule entry by job_id (or type for captain entries)."""
        reg = self._require_reg()
        _upsert_crew_schedule(reg, crew_id, job)

    def remove_schedule(self, crew_id: str, job_id: str) -> None:
        """Remove a schedule entry by job_id."""
        reg = self._require_reg()
        _remove_crew_schedule(reg, crew_id, job_id)

    def advance_next_fire_at(self, job: dict) -> None:
        """Mutate next_fire_at based on interval_secs or next cron tick."""
        _advance_next_fire_at(job)

    # ── Batch methods ─────────────────────────────────────────────────────────

    def write_batch(
        self,
        crew_id: str,
        batch_id: str,
        task_ids: list,
        status: str,
        created_at: str | None = None,
    ) -> dict | None:
        """Write (upsert) a batch entry. Delegates to ``_write_batch``."""
        return _write_batch(crew_id, batch_id, task_ids, status, created_at)

    def get_batch(self, crew_id: str, batch_id: str) -> dict | None:
        """Return the batch entry dict for *batch_id*, or None if not found."""
        return _get_batch(crew_id, batch_id)

    def update_batch_status(self, crew_id: str, batch_id: str, status: str) -> dict | None:
        """Update the ``status`` field of a batch entry atomically."""
        return _update_batch_status(crew_id, batch_id, status)

    def delete_batch(self, crew_id: str, batch_id: str) -> bool:
        """Remove a single batch entry by batch_id. Returns True if removed."""
        return _delete_batch(crew_id, batch_id)

    def find_batch_by_task_ids(self, crew_id: str, task_ids: list) -> dict | None:
        """Return the first batch entry whose task_ids set contains *task_ids*, or None."""
        return _find_batch_by_task_ids(crew_id, task_ids)

    # ── Secret methods ────────────────────────────────────────────────────────

    def write_secret(self, crew_id: str, secret: str) -> None:
        """Write the admiral signing secret for *crew_id*."""
        _write_crew_secret(crew_id, secret)

    def read_secret(self, crew_id: str) -> str | None:
        """Return the admiral signing secret for *crew_id*, or None if absent."""
        return _read_crew_secret(crew_id)

    def delete_secret(self, crew_id: str) -> None:
        """Remove the admiral signing-secret file for *crew_id*."""
        _delete_crew_secret(crew_id)


# Module-level singleton — import sites use:
#   from transport.registry import registry   (or: from registry import registry)
registry = CrewRegistry(REGISTRY_PATH)
