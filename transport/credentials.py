"""Backend credential store for the Ghost Academy transport (TRN-233).

One module owns every backend credential: storage, status, replacement,
clearing and per-launch resolution. Credentials are organised in a
per-backend subdirectory with one JSON envelope per profile at
``DATA_DIR/credentials/<backend>/<profile>.json`` (mode 0600, directory 0700):

    {"backend": "claude", "method": "setup-token", "stored_at": "<iso8601>",
     "provider": null, "payload": "<base64>"}

- ``payload`` is base64 of the raw secret bytes for static methods, the
  existing base64 SQLite rows for kiro device methods, and the tar bytes for
  Claude ``oauth`` / Codex ``chatgpt`` archives.
- ``provider`` is ``{"start_url", "region"}`` for kiro ``identity-center``.
- Writes go to a temp file in the same directory, then ``fsync``, then
  ``os.replace`` — atomic, so a crash mid-write leaves the previous file
  intact. (TRN-240's ``_write_secret_file`` truncates in place, so the store
  does not use it.)

Migration: On first access to the ``"default"`` profile, ``_migrate_flat_file``
atomically moves ``credentials/<backend>.json`` →
``credentials/<backend>/default.json``.

Every value read out of the store is passed through
``_security.register_secret`` so log redaction still applies. Status never
contains a payload or provider secret value.
"""
from __future__ import annotations

import base64
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:
    import security as _security  # container: flat /app/
except ModuleNotFoundError:
    from transport import security as _security  # local dev


# ── Supported backend/method matrix ───────────────────────────────────────────
# The method word here is the same word the HTTP routes, the CLI ``--method``
# flag and the status response use.
SUPPORTED_METHODS: dict[str, tuple[str, ...]] = {
    "kiro": ("api-key", "builder-id", "identity-center"),
    "claude": ("api-key", "setup-token", "oauth"),
    "codex": ("api-key", "chatgpt"),
}


class UnsupportedCredential(ValueError):
    """Raised for an unknown backend, or a backend/method pair not supported."""


def _validate(backend: str, method: str) -> None:
    methods = SUPPORTED_METHODS.get(backend)
    if methods is None:
        raise UnsupportedCredential(f"unknown backend {backend!r}")
    if method not in methods:
        raise UnsupportedCredential(
            f"backend {backend!r} does not support method {method!r} "
            f"(supported: {', '.join(methods)})"
        )


# ── Profile name validation ────────────────────────────────────────────────────
# A profile name must be lowercase alphanumeric, optionally with interior
# hyphens; 1–50 chars total; starts and ends with alphanumeric.
_PROFILE_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,48}[a-z0-9])?$")


def _validate_profile(profile: str, allow_default: bool = False) -> None:
    """Validate a profile name.

    Raises ``ValueError`` when:
    - The name does not match ``_PROFILE_RE`` (invalid format).
    - ``allow_default`` is ``False`` (the default) and ``profile == "default"``
      (the reserved name — HTTP callers must not supply it explicitly).

    Internal code that legitimately resolves to ``"default"`` (lazy migration,
    ``_resolve_profile`` fallback, backward-compat default args) must pass
    ``allow_default=True``.
    """
    if not _PROFILE_RE.match(profile):
        raise ValueError(
            f"invalid profile name {profile!r}: must be lowercase alphanumeric/hyphens, "
            "1-50 chars, start and end with alphanumeric"
        )
    if not allow_default and profile == "default":
        raise ValueError(
            "'default' is a reserved profile name and may not be supplied explicitly"
        )


class CredentialStore:
    """Per-profile credential store, persisted atomically under ``data_dir``.

    The store never keeps secret material in memory beyond the duration of a
    call; every ``get``/``put`` reads or writes the on-disk envelope.

    Layout: ``credentials/<backend>/<profile>.json`` (mode 0600, dir 0700).
    Migration from the old flat layout (``credentials/<backend>.json``) is done
    lazily on first access to the ``"default"`` profile for a backend.
    """

    def __init__(self, data_dir: Path | str = Path("/data")) -> None:
        self._dir = Path(data_dir) / "credentials"

    # ── paths ────────────────────────────────────────────────────────────────

    def _path(self, backend: str, profile: str = "default") -> Path:
        if backend not in SUPPORTED_METHODS:
            raise UnsupportedCredential(f"unknown backend {backend!r}")
        return self._dir / backend / f"{profile}.json"

    def _migrate_flat_file(self, backend: str) -> None:
        """Atomically migrate ``credentials/<backend>.json`` → ``credentials/<backend>/default.json``.

        Called at the start of every method that accesses the ``"default"``
        profile. Idempotent: a no-op when neither the flat file exists, or when
        the profile file already exists (in which case the flat file is removed).
        """
        flat = self._dir / f"{backend}.json"
        profile_dir = self._dir / backend
        profile_file = profile_dir / "default.json"
        if not flat.exists():
            return
        # Ensure the per-backend directory exists before moving.
        profile_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(str(profile_dir), 0o700)
        except OSError:
            pass
        if profile_file.exists():
            # Both exist — profile file wins; remove the stale flat file.
            try:
                flat.unlink()
            except OSError:
                pass
        else:
            # Move the flat file atomically into the per-profile slot.
            os.replace(str(flat), str(profile_file))
            try:
                os.chmod(str(profile_file), 0o600)
            except OSError:
                pass

    def _ensure_dir(self, backend: str) -> None:
        """Create ``credentials/`` and ``credentials/<backend>/`` with mode 0700."""
        self._dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(str(self._dir), 0o700)
        except OSError:
            pass
        backend_dir = self._dir / backend
        backend_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(str(backend_dir), 0o700)
        except OSError:
            pass

    # ── read ───────────────────────────────────────────────────────────────── 

    def get(self, backend: str, profile: str = "default") -> dict | None:
        """Return the stored credential envelope for *backend*/*profile*, or ``None``.

        The returned dict has keys ``backend``, ``method``, ``stored_at``,
        ``provider`` and ``payload`` (raw ``bytes``). The payload is registered
        for log redaction before it is returned.
        """
        _validate_profile(profile, allow_default=True)
        if profile == "default":
            self._migrate_flat_file(backend)
        path = self._path(backend, profile)
        try:
            raw = path.read_text()
        except FileNotFoundError:
            return None
        except OSError:
            return None
        try:
            env = json.loads(raw)
        except (ValueError, TypeError):
            return None
        payload_b64 = env.get("payload") or ""
        try:
            payload = base64.b64decode(payload_b64)
        except (ValueError, TypeError):
            return None
        # Register both the raw payload (static secrets are UTF-8 text) and the
        # base64 form so neither leaks into logs.
        if payload_b64:
            _security.register_secret(payload_b64)
        try:
            as_text = payload.decode("utf-8")
        except UnicodeDecodeError:
            as_text = ""
        if as_text:
            _security.register_secret(as_text)
        return {
            "backend": env.get("backend", backend),
            "method": env.get("method"),
            "stored_at": env.get("stored_at"),
            "provider": env.get("provider"),
            "payload": payload,
        }

    # ── write ──────────────────────────────────────────────────────────────── 

    def put(
        self,
        backend: str,
        method: str,
        payload: bytes | str,
        provider: dict | None = None,
        profile: str = "default",
    ) -> None:
        """Store (and replace) the credential for *backend*/*profile*.

        Atomic: writes a temp file in the per-backend credentials directory,
        ``fsync``s it, then ``os.replace``s it into place, so a crash mid-write
        leaves the previous credential intact.
        """
        _validate_profile(profile, allow_default=True)
        _validate(backend, method)
        if isinstance(payload, str):
            payload_bytes = payload.encode("utf-8")
        else:
            payload_bytes = payload
        envelope = {
            "backend": backend,
            "method": method,
            "stored_at": datetime.now(timezone.utc).isoformat(),
            "provider": provider,
            "payload": base64.b64encode(payload_bytes).decode("ascii"),
        }
        data = json.dumps(envelope).encode("utf-8")
        self._ensure_dir(backend)
        final = self._path(backend, profile)
        backend_dir = str(self._dir / backend)
        fd, tmp = tempfile.mkstemp(
            dir=backend_dir, prefix=f".{backend}-{profile}.", suffix=".tmp"
        )
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, str(final))
            os.chmod(str(final), 0o600)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        # fsync the directory so the rename is durable.
        try:
            dir_fd = os.open(backend_dir, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass

    # ── delete ─────────────────────────────────────────────────────────────── 

    def delete(self, backend: str, profile: str = "default") -> bool:
        """Remove *backend*/*profile*'s credential. Idempotent.

        Returns ``True`` when a file was removed and ``False`` when none
        existed. Raises ``OSError`` when the file exists but cannot be removed,
        so callers can tell "already logged out" apart from "still stored".
        """
        _validate_profile(profile, allow_default=True)
        if profile == "default":
            self._migrate_flat_file(backend)
        path = self._path(backend, profile)
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False

    # ── list profiles ─────────────────────────────────────────────────────────

    def list_profiles(self, backend: str) -> list[str]:
        """Return a sorted list of profile names for *backend*.

        Scans ``credentials/<backend>/`` for ``.json`` files and returns their
        stems (filenames without the ``.json`` extension). Returns ``[]`` when
        the directory does not exist or is empty.

        Triggers the flat-file migration for the ``"default"`` profile before
        scanning, so that an install upgraded from the old single-file layout
        (``credentials/<backend>.json``) returns ``["default"]`` rather than
        ``[]`` on the first call to this method.
        """
        if backend not in SUPPORTED_METHODS:
            raise UnsupportedCredential(f"unknown backend {backend!r}")
        # Trigger lazy migration so old-layout installs don't show an empty
        # list the first time this is called (e.g. GET /login/{backend}/profiles
        # before any get/put/delete call).
        self._migrate_flat_file(backend)
        backend_dir = self._dir / backend
        if not backend_dir.is_dir():
            return []
        stems: list[str] = []
        try:
            with os.scandir(str(backend_dir)) as it:
                for entry in it:
                    # follow_symlinks=False: exclude symlinks so an attacker who
                    # can write to the credentials directory cannot inject profile
                    # names via a symlink named <name>.json.
                    if entry.is_file(follow_symlinks=False) and entry.name.endswith(".json"):
                        stem = entry.name[:-5]  # strip ".json"
                        # Skip stems that are not valid profile names — this
                        # guards against crash residue, external tooling, or
                        # a previous layout leaving unexpected files, and
                        # prevents _resolve_profile's single-profile implicit
                        # selection from picking an unvalidated name.
                        if _PROFILE_RE.match(stem):
                            stems.append(stem)
        except OSError:
            return []
        return sorted(stems)

    # ── status ───────────────────────────────────────────────────────────────

    def status(self, profile: str = "default") -> dict:
        """Return a value-free status map for *profile*, one entry per supported backend.

        Each entry has ``configured`` (bool), ``method`` (or ``None``),
        ``stored_at`` (or ``None``) and ``provider`` (the non-secret
        ``start_url``/``region`` for identity-center, else ``None``). No payload
        or secret value ever appears.
        """
        _validate_profile(profile, allow_default=True)
        out: dict[str, dict] = {}
        for backend in SUPPORTED_METHODS:
            if profile == "default":
                self._migrate_flat_file(backend)
            path = self._path(backend, profile)
            try:
                env = json.loads(path.read_text())
            except (FileNotFoundError, OSError, ValueError, TypeError):
                out[backend] = {
                    "configured": False,
                    "method": None,
                    "stored_at": None,
                    "provider": None,
                }
                continue
            out[backend] = {
                "configured": True,
                "method": env.get("method"),
                "stored_at": env.get("stored_at"),
                "provider": env.get("provider"),
            }
        return out

    def status_all(self) -> dict[str, dict[str, dict]]:
        """Return a value-free status map for all profiles, all backends.

        Shape: ``{backend: {profile: {configured, method, stored_at, provider}}}``.
        Returns ``{backend: {}}`` when no profiles exist for a backend.
        No payload or secret value ever appears.
        """
        out: dict[str, dict[str, dict]] = {}
        for backend in SUPPORTED_METHODS:
            profiles = self.list_profiles(backend)
            out[backend] = {}
            for p in profiles:
                path = self._path(backend, p)
                try:
                    env = json.loads(path.read_text())
                except (FileNotFoundError, OSError, ValueError, TypeError):
                    out[backend][p] = {
                        "configured": False,
                        "method": None,
                        "stored_at": None,
                        "provider": None,
                    }
                    continue
                out[backend][p] = {
                    "configured": True,
                    "method": env.get("method"),
                    "stored_at": env.get("stored_at"),
                    "provider": env.get("provider"),
                }
        return out


class _MaskedCredential:
    """Wrapper whose ``__repr__`` never reveals the payload.

    Returned by nothing in the hot path, but available so callers that hold a
    credential dict can wrap it before logging.
    """

    __slots__ = ("backend", "method", "stored_at", "provider")

    def __init__(self, env: dict) -> None:
        self.backend = env.get("backend")
        self.method = env.get("method")
        self.stored_at = env.get("stored_at")
        self.provider = env.get("provider")

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"<Credential backend={self.backend!r} method={self.method!r} "
            f"stored_at={self.stored_at!r} payload=***MASKED***>"
        )


# Module-level default store pointing at the real data volume. Tests construct
# their own CredentialStore(tmp_path) and inject it; production callers use this.
try:
    _DATA_DIR = Path("/data")
    store = CredentialStore(_DATA_DIR)
except Exception:  # pragma: no cover - defensive
    store = CredentialStore(Path("/data"))
