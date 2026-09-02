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

try:
    from config import Config  # container: flat /app/
except ImportError:
    from transport.config import Config

cfg = Config.from_env()

DATA_DIR = Path(cfg.transport_data_dir)
REGISTRY_PATH = DATA_DIR / "crews.json"

logger = logging.getLogger(__name__)

# float("inf") is non-finite and raises ValueError in json.dumps; this value
# (≈ year 2286 Unix timestamp) is finite, JSON-serialisable, and practically
# unreachable as a real schedule time.
_NEVER_FIRE_AT: float = 9_999_999_999.0

_registry_lock = threading.Lock()


def _load_registry() -> dict:
    try:
        if REGISTRY_PATH.exists():
            return json.loads(REGISTRY_PATH.read_text())
    except Exception as e:
        logger.warning("Failed to load registry: %s", e)
    return {"crews": {}}


def _save_registry(reg: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = REGISTRY_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(reg, indent=2))
    os.replace(tmp, REGISTRY_PATH)
    os.chmod(REGISTRY_PATH, 0o600)


# ── Schedule registry helpers (TRN-29) ───────────────────────────────────────

def _get_crew_schedules(reg: dict, crew_id: str) -> list:
    """Return the schedules list for a crew, defaulting to []."""
    crew_entry = reg.get("crews", {}).get(crew_id, {})
    return crew_entry.get("schedules", [])


def _upsert_crew_schedule(reg: dict, crew_id: str, job: dict) -> None:
    """Insert or update a schedule entry by job_id."""
    crew_entry = reg.get("crews", {}).get(crew_id)
    if crew_entry is None:
        return
    schedules = crew_entry.setdefault("schedules", [])
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


# ── Per-crew signing-secret store (TRN-93) ───────────────────────────────────
# The admiral_secret is no longer written to crews.json (plaintext removed by
# TRN-93).  Instead, the transport stores it in a separate file under
# DATA_DIR/secrets/<crew_id>.admiral_secret (mode 0600).  This keeps the value
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
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(secret_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, secret.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


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
