"""File transfer — presigned URL signing/verification, tar member streaming,
staged uploads, and the /files GET/PUT handlers.

Depends on: podman (PodmanClient, _get_podman), lifecycle (_ensure_crew_running,
_require_crew), registry (indirectly via the crew lookup), config.

Import-direction note: _handle_file_get / _handle_file_put need
_ensure_crew_running and _require_crew from the orchestration layer
(lifecycle.py). lifecycle.py does not import files at module load time, so
importing lifecycle here at module load is cycle-free.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import logging
import os
import posixpath
import re
import secrets
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any, BinaryIO, Iterator
from urllib.parse import quote

import httpx2 as httpx
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response, StreamingResponse
from starlette.routing import Route

try:
    from config import Config  # container: flat /app/
except ImportError:
    from transport.config import Config

try:
    import security as _security  # container: flat /app/
except ImportError:
    from transport import security as _security

try:
    from podman import (  # container: flat /app/
        KIRO_WORKSPACE_ROOT,
        BUNDLE_STORAGE_ROOT,
        WORKER_MOUNT,
        PodmanClient,
        WorkerCommandError,
        WorkerImageMissing,
        _get_podman,
    )
except ModuleNotFoundError:
    from transport.podman import (  # local dev
        KIRO_WORKSPACE_ROOT,
        BUNDLE_STORAGE_ROOT,
        WORKER_MOUNT,
        PodmanClient,
        WorkerCommandError,
        WorkerImageMissing,
        _get_podman,
    )

# Crew orchestration helpers live in lifecycle.py.
# lifecycle.py does not import files at module load, so this is cycle-free.
# The lifecycle MODULE is imported (rather than the two names) so call sites
# resolve _ensure_crew_running / _require_crew through the live module object —
# preserving the call-site-patching contract the test suite relies on
# (patch.object(lifecycle, "_require_crew", ...)).
try:
    import lifecycle as _lifecycle  # container: flat /app/
except ModuleNotFoundError:
    from transport import lifecycle as _lifecycle  # local dev

# SCRIPTS_DIR canonical home is transport/constants.py.
# constants.py is a zero-dependency leaf, so importing it here is cycle-safe.
try:
    from constants import SCRIPTS_DIR  # container: flat /app/
except ModuleNotFoundError:
    from transport.constants import SCRIPTS_DIR  # local dev

logger = logging.getLogger(__name__)

cfg = Config.from_env()

PORT = cfg.port
DATA_DIR = Path("/data")
CREW_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,48}[a-z0-9]$|^[a-z0-9]$")

# SEC-01 — ref parameter validation
_REF_RE = re.compile(r"^[a-zA-Z0-9_./:@^~\-]+$")


class UploadTooLarge(ValueError):
    """An HTTP request exceeded its configured upload budget."""


class UploadBodyReadError(ValueError):
    """The request body could not be read to completion."""


class UploadBudgetExceeded(ValueError):
    """A confined transfer exceeded an archive or bundle storage budget."""


_TRANSFER_BUDGET_PREFIX = "TRANSFER_BUDGET_EXCEEDED:"


def _validate_ref(ref: str) -> str:
    """Validate a git ref parameter. Raises ValueError on invalid input."""
    if not ref:
        return ref
    if ref.startswith("-"):
        raise ValueError(f"ref must not start with '-': {ref!r}")
    if not _REF_RE.match(ref):
        raise ValueError(f"Invalid ref: {ref!r}")
    return ref


# SEC-02 — path traversal boundary enforcement
def _safe_workspace_path(workspace_root: str, raw_path: str) -> Path:
    """Resolve raw_path relative to workspace_root and verify it stays inside.
    Raises ValueError if the resolved path escapes the workspace root.
    """
    root = Path(workspace_root).resolve()
    clean = raw_path.lstrip("/")
    resolved = (root / clean).resolve()
    if resolved != root and not str(resolved).startswith(str(root) + "/"):
        raise ValueError(f"Path escapes workspace root: {raw_path!r}")
    return resolved


# ── File-URL signing secret ───────────────────────────────────────────────────

def _load_or_create_file_secret() -> str:
    """Load the persistent file-URL signing secret, generating it on first run.

    Persisted to DATA_DIR/ga-file-secret (0600) so supply/evac URLs survive
    transport restarts. GA_FILE_SECRET env var overrides (for testing).
    """
    if env_secret := os.environ.get("GA_FILE_SECRET", "").strip():
        return env_secret
    secret_path = DATA_DIR / "ga-file-secret"
    try:
        if secret_path.is_file():
            return secret_path.read_text().strip()
    except Exception:
        pass
    new_secret = secrets.token_hex(32)
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(secret_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.write(fd, new_secret.encode())
        os.close(fd)
    except Exception as e:
        logger.warning("Could not persist file secret to %s: %s", secret_path, e)
    return new_secret


_FILE_SECRET = _load_or_create_file_secret()
_security.register_secret(_FILE_SECRET)


# ── Presigned URLs ────────────────────────────────────────────────────────────

def _resolve_public_url_base() -> str:
    """Return the public URL base for presigned file URLs.

    Precedence: GA_HOST_URL > derived from ga-portal's published address
    (``http://localhost:{PORT}`` for a loopback or wildcard HOST).
    """
    return cfg.public_base_url()


def _sign_file_url(
    crew_id: str,
    path: str,
    ref: str | None = None,
    bundle: bool = False,
    pack: bool = False,
) -> str:
    """Return a short-lived presigned URL for a crew workspace file or bundle."""
    expires = int(time.time()) + 300
    flags = ":".join(sorted(f for f in ["bundle", "pack"] if (f == "bundle" and bundle) or (f == "pack" and pack)))
    payload = f"{crew_id}:{path}:{expires}:GET:{ref or ''}:{flags}"
    sig = hmac.HMAC(_FILE_SECRET.encode(), payload.encode(), digestmod=hashlib.sha256).hexdigest()
    base = _resolve_public_url_base()
    url = f"{base}/files/{crew_id}/{path}?expires={expires}&sig={sig}"
    if ref:
        url += f"&ref={quote(ref, safe='/')}"
    if bundle:
        url += "&bundle=1"
    if pack:
        url += "&pack=1"
    return url


def _verify_file_token(
    crew_id: str,
    path: str,
    expires: str,
    sig: str,
    ref: str | None = None,
    bundle: bool = False,
    mode: str | None = None,
    force: bool = False,
    pack: bool = False,
) -> bool:
    """Verify a presigned file URL token. Returns False if invalid or expired."""
    try:
        exp = int(expires)
    except (ValueError, TypeError):
        _security.audit_auth_event(action="verify_file_token", outcome="invalid", source=None)
        return False
    if time.time() > exp:
        _security.audit_auth_event(action="verify_file_token", outcome="expired", source=None)
        return False
    # Unified payload format: {crew_id}:{path}:{expires}:{method}:{ref}:{flags}
    # flags is a sorted colon-joined set of active boolean options (bundle, force, unpack for POST; bundle, pack for GET).
    # mode=None means GET (download); mode is a string ("", "unpack", "bundle") for POST (upload).
    if mode is not None:
        # Upload (POST) path — reconstruct flags the same way _sign_upload_url does
        flags = ":".join(sorted(f for f in ["bundle", "force", "unpack"] if (f == "bundle" and mode == "bundle") or (f == "force" and force) or (f == "unpack" and mode == "unpack")))
        payload = f"{crew_id}:{path}:{exp}:POST::{flags}"
    else:
        # Download (GET) path
        flags = ":".join(sorted(f for f in ["bundle", "pack"] if (f == "bundle" and bundle) or (f == "pack" and pack)))
        payload = f"{crew_id}:{path}:{exp}:GET:{ref or ''}:{flags}"
    expected = hmac.HMAC(_FILE_SECRET.encode(), payload.encode(), digestmod=hashlib.sha256).hexdigest()
    if hmac.compare_digest(expected, sig):
        _security.audit_auth_event(action="verify_file_token", outcome="valid", source=None)
        return True
    _security.audit_auth_event(action="verify_file_token", outcome="invalid", source=None)
    return False


def _sign_upload_url(crew_id: str, path: str, unpack: bool = False, bundle: bool = False, force: bool = False) -> str:
    """Return a short-lived presigned upload URL for a crew workspace path.

    The mode (unpack/bundle/force) is included in the signed HMAC payload so a
    token signed for a plain write cannot be replayed as an unpack or bundle
    clone, and a force flag cannot be added after signing.
    """
    expires = int(time.time()) + 300
    flags = ":".join(sorted(f for f in ["bundle", "force", "unpack"] if (f == "bundle" and bundle) or (f == "force" and force) or (f == "unpack" and unpack)))
    payload = f"{crew_id}:{path}:{expires}:POST::{flags}"
    sig = hmac.HMAC(_FILE_SECRET.encode(), payload.encode(), digestmod=hashlib.sha256).hexdigest()
    base = _resolve_public_url_base()
    return f"{base}/files/{crew_id}/{path}?expires={expires}&sig={sig}"


# ── Staged uploads ────────────────────────────────────────────────────────────

def _build_outer_transfer_tar(
    body: bytes | BinaryIO,
    workspace: str,
    body_size: int | None = None,
) -> tuple[str, str, BinaryIO, int]:
    """Wrap a disk-backed upload in a generated regular-file tar member."""
    transfer_id = secrets.token_hex(16)
    stage_name = f".kirocrew-transfer-{transfer_id}"
    workspace_root = workspace.rstrip("/")
    stage_dir = f"{workspace_root}/{stage_name}"
    member_name = f"{stage_name}/payload"

    source: BinaryIO
    if isinstance(body, bytes):
        source = io.BytesIO(body)
        body_size = len(body)
    else:
        source = body
    if body_size is None:
        current = source.tell()
        source.seek(0, os.SEEK_END)
        body_size = source.tell()
        source.seek(current)

    outer_tar = tempfile.TemporaryFile(mode="w+b")
    try:
        source.seek(0)
        with tarfile.open(fileobj=outer_tar, mode="w") as archive:
            member = tarfile.TarInfo(member_name)
            member.size = body_size
            member.mode = 0o600
            member.uid = 1000
            member.gid = 1000
            member.mtime = 0
            archive.addfile(member, source)
        outer_tar.flush()
        outer_tar_size = outer_tar.tell()
        outer_tar.seek(0)
        return stage_dir, f"{stage_dir}/payload", outer_tar, outer_tar_size
    except Exception:
        outer_tar.close()
        raise


async def _stream_request_body(request: Request, output: BinaryIO, max_bytes: int) -> int:
    """Receive an HTTP body into a temporary file without unbounded memory use."""
    total = 0
    stream = request.stream()
    try:
        async for chunk in stream:
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                raise UploadTooLarge(f"Upload exceeds the {max_bytes}-byte request limit")
            output.write(chunk)
    except UploadTooLarge:
        raise
    except Exception as exc:
        raise UploadBodyReadError(f"Could not read request body: {exc}") from exc
    finally:
        close_stream = getattr(stream, "aclose", None)
        if close_stream is not None:
            await close_stream()
    output.flush()
    output.seek(0)
    return total


def _cleanup_transfer_stage(
    podman: PodmanClient,
    container: str,
    stage_dir: str,
    workspace: str,
) -> None:
    """Best-effort cleanup for a stage whose transfer script did not start."""
    try:
        podman.container_exec_checked(
            container,
            ["python3", f"{SCRIPTS_DIR}/transfer_cleanup.py"],
            env={
                "GA_TRANSFER_STAGE": stage_dir,
                "GA_TRANSFER_WORKSPACE": workspace,
            },
        )
    except Exception:
        pass


def _worker_workspace_path(path: str, workspace: str) -> str:
    """Translate an absolute crew workspace path into the worker mount path."""
    relative = os.path.relpath(path, workspace)
    if relative == ".":
        return WORKER_MOUNT
    if relative == ".." or relative.startswith(f"..{os.sep}"):
        raise ValueError(f"Transfer path is outside the workspace: {path!r}")
    return posixpath.join(WORKER_MOUNT, *relative.split(os.sep))


def _transfer_upload(
    podman: PodmanClient,
    container: str,
    workspace: str,
    destination: str,
    body: bytes | BinaryIO,
    unpack: bool,
    bundle: bool = False,
    force: bool = False,
    *,
    body_size: int | None = None,
    volume_name: str | None = None,
) -> str:
    """Stage and write one upload without putting its bytes in exec inputs."""
    stage_dir, staged_file, outer_tar, outer_tar_size = _build_outer_transfer_tar(
        body, workspace, body_size
    )
    try:
        def chunks() -> Iterator[bytes]:
            while True:
                chunk = outer_tar.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk

        podman.container_archive_put(
            container, workspace, chunks(), content_length=outer_tar_size
        )
    except Exception:
        _cleanup_transfer_stage(podman, container, stage_dir, workspace)
        raise
    finally:
        outer_tar.close()

    cmd = ["python3", f"{SCRIPTS_DIR}/transfer_raw.py"]
    if unpack:
        cmd.append("--unpack")
    if bundle:
        cmd.append("--bundle")
    if force:
        cmd.append("--force")
    try:
        result = podman.worker_run(
            volume_name or podman.volume_name_for_crew(container.removeprefix("gs-")),
            cmd,
            env={
                "GA_TRANSFER_SOURCE": _worker_workspace_path(staged_file, workspace),
                "GA_TRANSFER_DEST": _worker_workspace_path(destination, workspace),
                "GA_TRANSFER_STAGE": _worker_workspace_path(stage_dir, workspace),
                "GA_TRANSFER_WORKSPACE": WORKER_MOUNT,
                "GA_TRANSFER_MAX_ARCHIVE_BYTES": str(cfg.ga_max_archive_bytes),
                "GA_TRANSFER_MAX_ARCHIVE_MEMBERS": str(cfg.ga_max_archive_members),
                "GA_TRANSFER_BUNDLE_STORAGE_ROOT": BUNDLE_STORAGE_ROOT,
                "GA_TRANSFER_BUNDLE_STORAGE_LIMIT_BYTES": str(
                    cfg.ga_max_bundle_storage_bytes
                ),
            },
            writable=True,
            tmpfs_size_bytes=cfg.ga_max_bundle_storage_bytes if bundle else None,
        )
        return result.decode("utf-8", errors="replace")
    except WorkerCommandError as exc:
        _cleanup_transfer_stage(podman, container, stage_dir, workspace)
        if exc.output.strip().startswith(_TRANSFER_BUDGET_PREFIX):
            raise UploadBudgetExceeded(exc.output.strip()) from exc
        raise
    except Exception:
        _cleanup_transfer_stage(podman, container, stage_dir, workspace)
        raise


# ── Stopped-crew worker helpers ───────────────────────────────────────────────
# These read files/bundles/diffs from a STOPPED crew's workspace volume by
# spinning up a disposable worker container (see PodmanClient.worker_run) that
# mounts the volume read-only. They never start the crew container and never
# update its idle timestamp. `path`/`repo_path` are workspace-relative and are
# expected to be already sanitised by the caller (no leading `/`, no `..`).

def worker_read_file(
    podman: PodmanClient, crew_id: str, path: str
) -> bytes:
    """Read a plain file from a stopped crew's volume via the worker sidecar.

    Returns the file bytes. Raises WorkerCommandError if the file does not
    exist (cat exits non-zero), WorkerImageMissing if the worker image is
    absent, or RuntimeError on other worker failures.
    """
    volume = podman.volume_name_for_crew(crew_id)
    target = posixpath.join(WORKER_MOUNT, path)
    return podman.worker_run(volume, ["cat", target])


def worker_git_bundle(
    podman: PodmanClient, crew_id: str, repo_path: str, ref: str | None = None
) -> bytes:
    """Create a git bundle from a stopped crew's repo via the worker sidecar.

    `repo_path` is the workspace-relative path to the repo (e.g. "repo").
    `ref` defaults to --all (bundle the entire history). Returns bundle bytes.
    """
    volume = podman.volume_name_for_crew(crew_id)
    repo_dir = posixpath.join(WORKER_MOUNT, repo_path) if repo_path else WORKER_MOUNT
    bundle_ref = ref if ref else "--all"
    # `git bundle create -` writes the bundle to stdout, so no temp file / no
    # writable mount is needed — the volume can stay read-only.
    # Note: `git bundle create` does not support `--` to end option processing;
    # injection is prevented by _validate_ref validating `ref` before this call.
    return podman.worker_run(
        volume,
        ["git", "-C", repo_dir, "bundle", "create", "-", bundle_ref],
    )


def worker_git_diff(
    podman: PodmanClient, crew_id: str, repo_path: str, ref: str,
    pathspec: str | None = None,
) -> str:
    """Produce a git diff from a stopped crew's repo via the worker sidecar.

    `repo_path` is the workspace-relative path to the repo. `pathspec`, when
    given, limits the diff to that path (mirrors the running path's
    `git diff <ref> -- <pathspec>`). Returns the diff as text.
    """
    volume = podman.volume_name_for_crew(crew_id)
    repo_dir = posixpath.join(WORKER_MOUNT, repo_path) if repo_path else WORKER_MOUNT
    cmd = ["git", "-C", repo_dir, "diff", ref]
    if pathspec is not None:
        cmd += ["--", pathspec]
    out = podman.worker_run(volume, cmd)
    return out.decode("utf-8", errors="replace")


# ── Tar member streaming ──────────────────────────────────────────────────────

class _ResponseChunkReader:
    """Expose an HTTPX byte iterator as the read API tarfile needs."""

    def __init__(self, chunks: Iterator[bytes]) -> None:
        self._chunks = iter(chunks)
        self._buffer = bytearray()
        self._eof = False

    def _fill(self, size: int) -> None:
        while not self._eof and (size < 0 or len(self._buffer) < size):
            try:
                chunk = next(self._chunks)
            except StopIteration:
                self._eof = True
                break
            if chunk:
                self._buffer.extend(chunk)

    def read(self, size: int = -1) -> bytes:
        if size == 0:
            return b""
        self._fill(size)
        if size < 0:
            size = len(self._buffer)
        result = bytes(self._buffer[:size])
        del self._buffer[:size]
        return result


class _TarMemberStream:
    """Stream one regular file member from a raw Podman archive response."""

    def __init__(self, response: httpx.Response, expected_path: str) -> None:
        self._response = response
        self._reader = _ResponseChunkReader(response.iter_bytes())
        self._tar: tarfile.TarFile | None = None
        self._member_file: Any | None = None
        self._closed = False
        try:
            self._tar = tarfile.open(fileobj=self._reader, mode="r|*")
            expected = posixpath.normpath(expected_path.lstrip("/"))
            expected_names = {expected, posixpath.basename(expected)}
            selected = None
            for member in self._tar:
                member_name = posixpath.normpath(member.name).lstrip("/")
                if member_name in expected_names:
                    selected = member
                    break
            if selected is None:
                raise ValueError(
                    f"Podman archive did not contain {expected_path}"
                )
            if not selected.isreg():
                raise ValueError(
                    f"Podman archive member is not a regular file: {expected_path}"
                )
            self._member_file = self._tar.extractfile(selected)
            if self._member_file is None:
                raise ValueError(
                    f"Podman archive member could not be read: {expected_path}"
                )
        except Exception:
            self.close()
            raise

    def __iter__(self) -> Iterator[bytes]:
        try:
            while True:
                chunk = self._member_file.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._member_file is not None:
            try:
                self._member_file.close()
            except Exception:
                pass
        if self._tar is not None:
            try:
                self._tar.close()
            except Exception:
                pass
        try:
            self._response.close()
        except Exception:
            pass


# ── HTTP handlers ─────────────────────────────────────────────────────────────

async def _handle_file_get(request: Request) -> Response:
    """Serve a file, git diff, or git bundle from a crew workspace.

    GET /files/{crew_id}/{path}?expires=<ts>&sig=<hmac> — stream file
    GET /files/{crew_id}/{path}?expires=<ts>&sig=<hmac>&ref=HEAD — diff
    GET /files/{crew_id}/{path}?expires=<ts>&sig=<hmac>&bundle=1 — git bundle
    GET /files/{crew_id}/{path}?expires=<ts>&sig=<hmac>&pack=1 — directory tar
    Token is short-lived (300, default 5 min).
    """
    crew_id = request.path_params.get("crew_id", "")
    path = request.path_params.get("path", "")
    ref = request.query_params.get("ref")
    bundle = request.query_params.get("bundle", "0") in ("1", "true", "yes")
    pack = request.query_params.get("pack", "0") in ("1", "true", "yes")
    expires = request.query_params.get("expires", "")
    sig = request.query_params.get("sig", "")

    if not CREW_ID_RE.fullmatch(crew_id):
        return PlainTextResponse("Invalid crew_id", status_code=400)

    if pack and bundle:
        return PlainTextResponse("pack and bundle cannot both be enabled", status_code=400)

    if not _verify_file_token(crew_id, path, expires, sig, ref, bundle, pack=pack):
        return PlainTextResponse("Forbidden", status_code=403)

    # SEC-01: validate ref before any git invocation
    try:
        ref = _validate_ref(ref) if ref else ref
    except ValueError as e:
        return PlainTextResponse(str(e), status_code=400)

    # SEC-02: resolve path and enforce workspace boundary
    try:
        _safe_workspace_path(KIRO_WORKSPACE_ROOT, path)
    except ValueError as e:
        return PlainTextResponse(str(e), status_code=400)

    # Sanitise path — no traversal outside workspace
    clean = path.lstrip("/")
    if not clean:
        return PlainTextResponse("Invalid path", status_code=400)

    try:
        crew = _lifecycle._require_crew(crew_id)
    except (ValueError, KeyError, RuntimeError) as e:
        return PlainTextResponse(str(e), status_code=404)

    podman = _get_podman()
    ws = KIRO_WORKSPACE_ROOT

    c = _lifecycle._to_crew(crew_id, crew)

    # ── Stopped-crew path ─────────────────────────────────────────────────────
    # If the crew container is not running, serve the read via a disposable
    # worker container mounting the crew volume read-only. This does NOT wake
    # the crew container and does NOT update its idle timestamp (no _touch_crew,
    # no _ensure_crew_running).
    try:
        running = podman.container_is_running(c.container)
    except Exception:
        running = False

    if not running:
        try:
            if bundle:
                data = worker_git_bundle(podman, crew_id, clean, ref)
                return Response(data, media_type="application/octet-stream")
            if ref:
                # Diff is rooted at the repo/ dir, matching the running path.
                repo_pathspec = clean.removeprefix("repo/") or "."
                if repo_pathspec == "repo":
                    repo_pathspec = "."
                out = worker_git_diff(
                    podman, crew_id, "repo", ref, pathspec=repo_pathspec
                )
                return PlainTextResponse(out, media_type="text/plain")
            if pack:
                # Directory extraction from a stopped crew: use the Podman archive
                # API directly (same path as stopped-crew plain-file evac). The
                # Podman archive API operates on both running and stopped containers
                # via the overlay filesystem. No worker container needed — a
                # directory tar requires no git process.
                archive_response = podman.container_archive_get(
                    c.container, f"{ws}/{clean}"
                )
                return StreamingResponse(
                    archive_response.iter_bytes(), media_type="application/x-tar"
                )
            # Plain file on a stopped crew: use archive API directly (no worker,
            # no _ensure_crew_running). The Podman archive API works on both
            # running and stopped containers via the overlay filesystem.
            archive_response = podman.container_archive_get(
                c.container, f"{ws}/{clean}"
            )
            archive_stream = _TarMemberStream(archive_response, clean)
            ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
            media_types = {
                "json": "application/json", "md": "text/markdown",
                "txt": "text/plain", "py": "text/x-python",
                "js": "text/javascript", "ts": "text/typescript",
                "html": "text/html", "css": "text/css",
                "sh": "text/x-sh", "yaml": "text/yaml", "yml": "text/yaml",
            }
            media_type = media_types.get(ext, "application/octet-stream")
            return StreamingResponse(iter(archive_stream), media_type=media_type)
        except WorkerImageMissing as e:
            return PlainTextResponse(str(e), status_code=500)
        except WorkerCommandError as e:
            # A git failure (not a repo, bad ref) → 500 with git stderr.
            return PlainTextResponse(e.output.strip() or str(e), status_code=500)
        except Exception as e:
            msg = str(e)
            # Podman archive GET returns HTTP 404 when the path does not exist
            # inside the container.
            if "404" in msg and ("no such file" in msg.lower() or "not found" in msg.lower()):
                return PlainTextResponse(f"Not found: {path}", status_code=404)
            return PlainTextResponse(msg, status_code=500)

    # ── Running-crew path (unchanged) ─────────────────────────────────────────
    try:
        crew = _lifecycle._ensure_crew_running(crew, crew_id)
    except (ValueError, KeyError, RuntimeError) as e:
        return PlainTextResponse(str(e), status_code=404)

    c = _lifecycle._to_crew(crew_id, crew)

    try:
        if bundle:
            repo_root = os.path.join(ws, clean)
            bundle_path = f"{ws}/.kirocrew-bundle-{secrets.token_hex(16)}.bundle"
            try:
                bundle_ref = ref if ref else "--all"
                # Note: `git bundle create` does not support `--` to end option
                # processing; injection is prevented by _validate_ref validating
                # `ref` before any git invocation.
                podman.container_exec_checked(
                    c.container,
                    ["git", "-C", repo_root, "bundle", "create", bundle_path, bundle_ref],
                )
                archive_response = podman.container_archive_get(
                    c.container, bundle_path
                )
            except Exception:
                try:
                    podman.container_exec_checked(
                        c.container, ["rm", "-f", bundle_path]
                    )
                except Exception:
                    pass
                raise

            try:
                # Validate the archive before creating a 200 streaming response so
                # malformed Podman output follows the normal error path.
                archive_stream = _TarMemberStream(archive_response, bundle_path)
            except Exception:
                try:
                    podman.container_exec_checked(
                        c.container, ["rm", "-f", bundle_path]
                    )
                except Exception:
                    pass
                raise

            def stream_bundle() -> Iterator[bytes]:
                try:
                    yield from archive_stream
                finally:
                    archive_stream.close()
                    try:
                        podman.container_exec_checked(
                            c.container, ["rm", "-f", bundle_path]
                        )
                    except Exception as cleanup_error:
                        logger.warning(
                            "Failed to remove temporary bundle %s: %s",
                            bundle_path,
                            cleanup_error,
                        )

            return StreamingResponse(
                stream_bundle(), media_type="application/octet-stream"
            )
        if ref:
            repo_path = clean.removeprefix("repo/") or "."
            if repo_path == "repo":
                repo_path = "."
            out = podman.container_exec(
                c.container,
                ["git", "-C", os.path.join(ws, "repo"), "diff", ref, "--", repo_path],
            )
            return PlainTextResponse(out, media_type="text/plain")
        if pack:
            archive_response = podman.container_archive_get(
                c.container, f"{ws}/{clean}"
            )
            return StreamingResponse(
                archive_response.iter_bytes(), media_type="application/x-tar"
            )
        archive_response = podman.container_archive_get(
            c.container, f"{ws}/{clean}"
        )
        archive_stream = _TarMemberStream(archive_response, clean)
        # Guess content type from extension
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        media_types = {
            "json": "application/json", "md": "text/markdown",
            "txt": "text/plain", "py": "text/x-python",
            "js": "text/javascript", "ts": "text/typescript",
            "html": "text/html", "css": "text/css",
            "sh": "text/x-sh", "yaml": "text/yaml", "yml": "text/yaml",
        }
        media_type = media_types.get(ext, "application/octet-stream")
        return StreamingResponse(iter(archive_stream), media_type=media_type)
    except Exception as e:
        msg = str(e)
        # Podman archive GET returns HTTP 404 when the path does not exist inside
        # the container. Surface that as a 404 to the caller rather than a 500.
        if "404" in msg and ("no such file" in msg.lower() or "not found" in msg.lower()):
            return PlainTextResponse(f"Not found: {path}", status_code=404)
        return PlainTextResponse(msg, status_code=500)


async def _handle_file_put(request: Request) -> Response:
    """Inject a file or tar archive into a crew workspace.

    POST /files/{crew_id}/{path}?expires=<ts>&sig=<hmac>
      Body: raw file bytes

    POST /files/{crew_id}/{path}?expires=<ts>&sig=<hmac>&unpack=1
      Body: .tar or .tar.gz bytes — unpacked at {path} in the workspace.
      If path is "." or empty, unpacks at workspace root.

    POST /files/{crew_id}/{path}?expires=<ts>&sig=<hmac>&bundle=1
      Body: git bundle bytes — cloned into {path} in the workspace.

    Token is short-lived (300, default 5 min).
    Intermediate directories are created automatically.
    """
    crew_id = request.path_params.get("crew_id", "")
    path = request.path_params.get("path", "")
    expires = request.query_params.get("expires", "")
    sig = request.query_params.get("sig", "")
    unpack = request.query_params.get("unpack", "0") in ("1", "true", "yes")
    bundle = request.query_params.get("bundle", "0") in ("1", "true", "yes")
    force = request.query_params.get("force", "0") in ("1", "true", "yes")

    if not CREW_ID_RE.fullmatch(crew_id):
        return PlainTextResponse("Invalid crew_id", status_code=400)

    if unpack and bundle:
        return PlainTextResponse("unpack and bundle cannot both be enabled", status_code=400)

    mode = "unpack" if unpack else ("bundle" if bundle else "")
    if not _verify_file_token(crew_id, path, expires, sig, mode=mode, force=force):
        return PlainTextResponse("Forbidden", status_code=403)

    # SEC-02: resolve path and enforce workspace boundary
    try:
        _safe_workspace_path(KIRO_WORKSPACE_ROOT, path)
    except ValueError as e:
        return PlainTextResponse(str(e), status_code=400)

    # Sanitise path — no traversal outside workspace
    clean = path.lstrip("/")

    try:
        crew = _lifecycle._require_crew(crew_id)
    except (ValueError, KeyError, RuntimeError) as e:
        return PlainTextResponse(str(e), status_code=404)

    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except (TypeError, ValueError):
            return PlainTextResponse("Invalid Content-Length", status_code=400)
        if declared_length < 0:
            return PlainTextResponse("Invalid Content-Length", status_code=400)
        if declared_length > cfg.ga_max_upload_bytes:
            return PlainTextResponse(
                f"Upload exceeds the {cfg.ga_max_upload_bytes}-byte request limit",
                status_code=413,
            )

    with tempfile.TemporaryFile(mode="w+b") as body_file:
        try:
            body_size = await _stream_request_body(
                request, body_file, cfg.ga_max_upload_bytes
            )
        except UploadTooLarge as e:
            return PlainTextResponse(str(e), status_code=413)
        except UploadBodyReadError as e:
            return PlainTextResponse(str(e), status_code=400)
        if body_size == 0:
            return PlainTextResponse("Empty body", status_code=400)

        try:
            crew = _lifecycle._ensure_crew_running(crew, crew_id)
        except (ValueError, KeyError, RuntimeError) as e:
            return PlainTextResponse(str(e), status_code=404)

        podman = _get_podman()
        ws = KIRO_WORKSPACE_ROOT
        if unpack:
            destination = f"{ws}/{clean}".rstrip("/") if clean and clean != "." else ws
            fallback = f"unpacked to {destination}"
        else:
            destination = f"{ws}/{clean}" if clean else ws
            fallback = f"cloned to {destination}" if bundle else f"wrote to {destination}"

        try:
            result = _transfer_upload(
                podman,
                _lifecycle._to_crew(crew_id, crew).container,
                ws,
                destination,
                body_file,
                unpack,
                bundle,
                force,
                body_size=body_size,
                volume_name=podman.volume_name_for_crew(crew_id),
            )
            return PlainTextResponse(result.strip() or fallback)
        except UploadBudgetExceeded as e:
            return PlainTextResponse(str(e), status_code=413)
        except Exception as e:
            return PlainTextResponse(str(e), status_code=500)


file_routes = [
    Route("/files/{crew_id}/{path:path}", _handle_file_get, methods=["GET"]),
    Route("/files/{crew_id}/{path:path}", _handle_file_put, methods=["POST"]),
]
