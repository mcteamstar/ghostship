"""Backend credential store for the Ghost Academy transport (TRN-233).

One module owns every backend credential: storage, status, replacement,
clearing and per-launch resolution. Each backend gets a single JSON envelope
at ``DATA_DIR/credentials/<backend>.json`` (mode 0600, directory 0700):

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

Every value read out of the store is passed through
``_security.register_secret`` so log redaction still applies. Status never
contains a payload or provider secret value.
"""
from __future__ import annotations

import base64
import json
import os
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


class CredentialStore:
    """One active credential per backend, persisted atomically under ``data_dir``.

    The store never keeps secret material in memory beyond the duration of a
    call; every ``get``/``put`` reads or writes the on-disk envelope.
    """

    def __init__(self, data_dir: Path | str = Path("/data")) -> None:
        self._dir = Path(data_dir) / "credentials"

    # ── paths ────────────────────────────────────────────────────────────────

    def _path(self, backend: str) -> Path:
        if backend not in SUPPORTED_METHODS:
            raise UnsupportedCredential(f"unknown backend {backend!r}")
        return self._dir / f"{backend}.json"

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self._dir, 0o700)
        except OSError:
            pass

    # ── read ───────────────────────────────────────────────────────────────── 

    def get(self, backend: str) -> dict | None:
        """Return the stored credential envelope for *backend*, or ``None``.

        The returned dict has keys ``backend``, ``method``, ``stored_at``,
        ``provider`` and ``payload`` (raw ``bytes``). The payload is registered
        for log redaction before it is returned.
        """
        path = self._path(backend)
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
    ) -> None:
        """Store (and replace) the credential for *backend*.

        Atomic: writes a temp file in the credentials directory, ``fsync``s it,
        then ``os.replace``s it into place, so a crash mid-write leaves the
        previous credential intact. One active credential per backend — this
        overwrites whatever that backend held before.
        """
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
        self._ensure_dir()
        final = self._path(backend)
        fd, tmp = tempfile.mkstemp(dir=str(self._dir), prefix=f".{backend}.", suffix=".tmp")
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, final)
            os.chmod(final, 0o600)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        # fsync the directory so the rename is durable.
        try:
            dir_fd = os.open(str(self._dir), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass

    # ── delete ─────────────────────────────────────────────────────────────── 

    def delete(self, backend: str) -> bool:
        """Remove *backend*'s credential. Idempotent.

        Returns ``True`` when a file was removed and ``False`` when none
        existed. Raises ``OSError`` when the file exists but cannot be removed,
        so callers can tell "already logged out" apart from "still stored".
        """
        path = self._path(backend)
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False

    # ── status ───────────────────────────────────────────────────────────────

    def status(self) -> dict:
        """Return a value-free status map, one entry per supported backend.

        Each entry has ``configured`` (bool), ``method`` (or ``None``),
        ``stored_at`` (or ``None``) and ``provider`` (the non-secret
        ``start_url``/``region`` for identity-center, else ``None``). No payload
        or secret value ever appears.
        """
        out: dict[str, dict] = {}
        for backend in SUPPORTED_METHODS:
            path = self._path(backend)
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
