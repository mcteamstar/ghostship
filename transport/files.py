"""File transfer — presigned URL signing/verification, tar member streaming,
staged uploads, and the /files GET/PUT handlers.

Depends on: podman (PodmanClient, _get_podman), registry (indirectly via the
crew lookup done through the lazily-imported orchestration helpers), config.

Circular-import note: _handle_file_get / _handle_file_put need
_ensure_crew_running and _require_crew, which live in the orchestration layer
(server.py today, lifecycle.py after step 5 of TRN-71). Importing that layer at
module load time would create a cycle (server imports files, files imports
server). We resolve those two functions lazily at call time via
_crew_helpers(), which tries lifecycle first and falls back to server, so this
module keeps only the leaf-level static dependencies the design prescribes.
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
import time
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote

import httpx
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
        WORKER_MOUNT,
        PodmanClient,
        WorkerCommandError,
        WorkerImageMissing,
        _get_podman,
    )
except ModuleNotFoundError:
    from transport.podman import (  # local dev
        KIRO_WORKSPACE_ROOT,
        WORKER_MOUNT,
        PodmanClient,
        WorkerCommandError,
        WorkerImageMissing,
        _get_podman,
    )

logger = logging.getLogger(__name__)

cfg = Config.from_env()

PORT = cfg.port
DATA_DIR = Path(cfg.transport_data_dir)
GA_FILE_TTL_SECS = cfg.ga_file_ttl_secs  # 5 min default
SCRIPTS_DIR = "/scripts"
CREW_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,48}[a-z0-9]$|^[a-z0-9]$")


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


# ── Crew orchestration helpers (lazy — see circular-import note above) ─────────

def _crew_helpers() -> tuple[Any, Any]:
    """Resolve (_ensure_crew_running, _require_crew) from the orchestration layer.

    Tries lifecycle.py first (post step-5 home), then falls back to server.py
    (their home during step 3). Resolved lazily so this module has no static
    dependency on either, avoiding the import cycle.
    """
    try:
        from lifecycle import _ensure_crew_running, _require_crew  # container
        return _ensure_crew_running, _require_crew
    except ImportError:
        pass
    try:
        from transport.lifecycle import _ensure_crew_running, _require_crew
        return _ensure_crew_running, _require_crew
    except ImportError:
        pass
    try:
        from server import _ensure_crew_running, _require_crew  # container
        return _ensure_crew_running, _require_crew
    except ImportError:
        from transport.server import _ensure_crew_running, _require_crew
        return _ensure_crew_running, _require_crew


# ── Presigned URLs ────────────────────────────────────────────────────────────

def _resolve_public_url_base() -> str:
    """Return the public URL base for presigned file URLs.

    Precedence: GA_HOST_URL > http://localhost:{PORT}.
    """
    base = cfg.ga_host_url
    if base:
        return base.rstrip("/")
    return f"http://localhost:{PORT}"


def _sign_file_url(
    crew_id: str,
    path: str,
    ref: str | None = None,
    bundle: bool = False,
) -> str:
    """Return a short-lived presigned URL for a crew workspace file or bundle."""
    expires = int(time.time()) + GA_FILE_TTL_SECS
    flags = ":".join(sorted(f for f in ["bundle"] if bundle))
    payload = f"{crew_id}:{path}:{expires}:GET:{ref or ''}:{flags}"
    sig = hmac.new(_FILE_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    base = _resolve_public_url_base()
    url = f"{base}/files/{crew_id}/{path}?expires={expires}&sig={sig}"
    if ref:
        url += f"&ref={quote(ref, safe='/')}"
    if bundle:
        url += "&bundle=1"
    return url


def _verify_file_token(
    crew_id: str,
    path: str,
    expires: str,
    sig: str,
    ref: str | None = None,
    bundle: bool = False,
    mode: str | None = None,
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
    # flags is a sorted colon-joined set of active boolean options (bundle, unpack).
    # mode=None means GET (download); mode is a string ("", "unpack", "bundle") for POST (upload).
    if mode is not None:
        # Upload (POST) path — reconstruct flags the same way _sign_upload_url does
        flags = ":".join(sorted(f for f in ["bundle", "unpack"] if (f == "bundle" and mode == "bundle") or (f == "unpack" and mode == "unpack")))
        payload = f"{crew_id}:{path}:{exp}:POST::{flags}"
    else:
        # Download (GET) path
        flags = ":".join(sorted(f for f in ["bundle"] if bundle))
        payload = f"{crew_id}:{path}:{exp}:GET:{ref or ''}:{flags}"
    expected = hmac.new(_FILE_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if hmac.compare_digest(expected, sig):
        _security.audit_auth_event(action="verify_file_token", outcome="valid", source=None)
        return True
    _security.audit_auth_event(action="verify_file_token", outcome="invalid", source=None)
    return False


def _sign_upload_url(crew_id: str, path: str, unpack: bool = False, bundle: bool = False) -> str:
    """Return a short-lived presigned upload URL for a crew workspace path.

    The mode (unpack/bundle) is included in the signed HMAC payload so a token
    signed for a plain write cannot be replayed as an unpack or bundle clone.
    """
    expires = int(time.time()) + GA_FILE_TTL_SECS
    flags = ":".join(sorted(f for f in ["bundle", "unpack"] if (f == "bundle" and bundle) or (f == "unpack" and unpack)))
    payload = f"{crew_id}:{path}:{expires}:POST::{flags}"
    sig = hmac.new(_FILE_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    base = _resolve_public_url_base()
    return f"{base}/files/{crew_id}/{path}?expires={expires}&sig={sig}"


# ── Staged uploads ────────────────────────────────────────────────────────────

def _build_outer_transfer_tar(
    body: bytes,
    workspace: str,
) -> tuple[str, str, bytes]:
    """Wrap upload bytes in one generated regular-file tar member."""
    transfer_id = secrets.token_hex(16)
    stage_name = f".kirocrew-transfer-{transfer_id}"
    workspace_root = workspace.rstrip("/")
    stage_dir = f"{workspace_root}/{stage_name}"
    member_name = f"{stage_name}/payload"

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        member = tarfile.TarInfo(member_name)
        member.size = len(body)
        member.mode = 0o600
        member.mtime = 0
        archive.addfile(member, io.BytesIO(body))
    return stage_dir, f"{stage_dir}/payload", buffer.getvalue()


def _cleanup_transfer_stage(
    podman: PodmanClient,
    container: str,
    stage_dir: str,
) -> None:
    """Best-effort cleanup for a stage whose transfer script did not start."""
    try:
        podman.container_exec_checked(
            container,
            ["python3", f"{SCRIPTS_DIR}/transfer_cleanup.py"],
            env={"GA_TRANSFER_STAGE": stage_dir},
        )
    except Exception:
        pass


def _transfer_upload(
    podman: PodmanClient,
    container: str,
    workspace: str,
    destination: str,
    body: bytes,
    unpack: bool,
    bundle: bool = False,
) -> str:
    """Stage and write one upload without putting its bytes in exec inputs."""
    stage_dir, staged_file, outer_tar = _build_outer_transfer_tar(body, workspace)
    try:
        podman.container_archive_put(container, workspace, outer_tar)
    except Exception:
        _cleanup_transfer_stage(podman, container, stage_dir)
        raise

    if bundle:
        try:
            parent = os.path.dirname(destination.rstrip("/")) or workspace
            podman.container_exec_checked(container, ["mkdir", "-p", parent])
            # Clone the bundle. If the bundle's HEAD ref contains a slash
            # (e.g. release/0.2.4) git may fail to resolve it and leave the
            # working tree empty. Detect that and check out explicitly.
            result = podman.container_exec_checked(
                container, ["git", "clone", staged_file, destination]
            )
            # Check if clone left an empty working tree (no HEAD commit).
            try:
                podman.container_exec_checked(
                    container, ["git", "-C", destination, "rev-parse", "HEAD"]
                )
            except RuntimeError:
                # HEAD unresolvable — check out the first available remote branch.
                # Use list-form exec calls (no shell, no interpolation) to avoid
                # shell injection via the destination path.
                branches_output = podman.container_exec_checked(
                    container, ["git", "-C", destination, "branch", "-r"]
                )
                # Parse remote branches in Python; skip the HEAD pointer line.
                branch = ""
                for line in branches_output.splitlines():
                    stripped = line.strip()
                    if stripped and "HEAD" not in stripped:
                        # Strip "origin/" prefix to get the local branch name.
                        branch = stripped.removeprefix("origin/").strip()
                        break
                if branch:
                    podman.container_exec_checked(
                        container,
                        ["git", "-C", destination, "checkout", "-b", branch, f"origin/{branch}"],
                    )
            return result
        finally:
            _cleanup_transfer_stage(podman, container, stage_dir)

    try:
        cmd = ["python3", f"{SCRIPTS_DIR}/transfer_raw.py"]
        if unpack:
            cmd.append("--unpack")
        return podman.container_exec_checked(
            container,
            cmd,
            env={
                "GA_TRANSFER_SOURCE": staged_file,
                "GA_TRANSFER_DEST": destination,
                "GA_TRANSFER_STAGE": stage_dir,
            },
        )
    except Exception:
        _cleanup_transfer_stage(podman, container, stage_dir)
        raise


# ── Stopped-crew worker helpers (TRN-81) ──────────────────────────────────────
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
    Token is short-lived (GA_FILE_TTL_SECS, default 5 min).
    """
    crew_id = request.path_params.get("crew_id", "")
    path = request.path_params.get("path", "")
    ref = request.query_params.get("ref")
    bundle = request.query_params.get("bundle", "0") in ("1", "true", "yes")
    expires = request.query_params.get("expires", "")
    sig = request.query_params.get("sig", "")

    if not CREW_ID_RE.fullmatch(crew_id):
        return PlainTextResponse("Invalid crew_id", status_code=400)

    if not _verify_file_token(crew_id, path, expires, sig, ref, bundle):
        return PlainTextResponse("Forbidden", status_code=403)

    # Sanitise path — no traversal outside workspace
    clean = path.lstrip("/")
    if not clean:
        return PlainTextResponse("Invalid path", status_code=400)
    if ".." in clean.split("/"):
        return PlainTextResponse("Invalid path", status_code=400)

    _ensure_crew_running, _require_crew = _crew_helpers()
    try:
        crew = _require_crew(crew_id)
    except (ValueError, KeyError, RuntimeError) as e:
        return PlainTextResponse(str(e), status_code=404)

    podman = _get_podman()
    ws = KIRO_WORKSPACE_ROOT

    # ── Stopped-crew path (TRN-81) ────────────────────────────────────────────
    # If the crew container is not running, serve the read via a disposable
    # worker container mounting the crew volume read-only. This does NOT wake
    # the crew container and does NOT update its idle timestamp (no _touch_crew,
    # no _ensure_crew_running).
    try:
        running = podman.container_is_running(crew["container"])
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
            # Plain file on a stopped crew: use archive API directly (no worker,
            # no _ensure_crew_running). The Podman archive API works on both
            # running and stopped containers via the overlay filesystem.
            archive_response = podman.container_archive_get(
                crew["container"], f"{ws}/{clean}"
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
        crew = _ensure_crew_running(crew, crew_id)
    except (ValueError, KeyError, RuntimeError) as e:
        return PlainTextResponse(str(e), status_code=404)

    try:
        if bundle:
            repo_root = os.path.join(ws, clean)
            bundle_path = f"{ws}/.kirocrew-bundle-{secrets.token_hex(16)}.bundle"
            try:
                bundle_ref = ref if ref else "--all"
                podman.container_exec_checked(
                    crew["container"],
                    ["git", "-C", repo_root, "bundle", "create", bundle_path, bundle_ref],
                )
                archive_response = podman.container_archive_get(
                    crew["container"], bundle_path
                )
            except Exception:
                try:
                    podman.container_exec_checked(
                        crew["container"], ["rm", "-f", bundle_path]
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
                        crew["container"], ["rm", "-f", bundle_path]
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
                            crew["container"], ["rm", "-f", bundle_path]
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
                crew["container"],
                ["git", "-C", os.path.join(ws, "repo"), "diff", ref, "--", repo_path],
            )
            return PlainTextResponse(out, media_type="text/plain")
        archive_response = podman.container_archive_get(
            crew["container"], f"{ws}/{clean}"
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

    Token is short-lived (GA_FILE_TTL_SECS, default 5 min).
    Intermediate directories are created automatically.
    """
    crew_id = request.path_params.get("crew_id", "")
    path = request.path_params.get("path", "")
    expires = request.query_params.get("expires", "")
    sig = request.query_params.get("sig", "")
    unpack = request.query_params.get("unpack", "0") in ("1", "true", "yes")
    bundle = request.query_params.get("bundle", "0") in ("1", "true", "yes")

    if not CREW_ID_RE.fullmatch(crew_id):
        return PlainTextResponse("Invalid crew_id", status_code=400)

    if unpack and bundle:
        return PlainTextResponse("unpack and bundle cannot both be enabled", status_code=400)

    mode = "unpack" if unpack else ("bundle" if bundle else "")
    if not _verify_file_token(crew_id, path, expires, sig, mode=mode):
        return PlainTextResponse("Forbidden", status_code=403)

    # Sanitise path — no traversal outside workspace
    clean = path.lstrip("/")
    if ".." in clean.split("/"):
        return PlainTextResponse("Invalid path", status_code=400)

    _ensure_crew_running, _require_crew = _crew_helpers()
    try:
        crew = _ensure_crew_running(_require_crew(crew_id), crew_id)
    except (ValueError, KeyError, RuntimeError) as e:
        return PlainTextResponse(str(e), status_code=404)

    body = await request.body()
    if not body:
        return PlainTextResponse("Empty body", status_code=400)

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
            crew["container"],
            ws,
            destination,
            body,
            unpack,
            bundle,
        )
        return PlainTextResponse(result.strip() or fallback)
    except Exception as e:
        return PlainTextResponse(str(e), status_code=500)


file_routes = [
    Route("/files/{crew_id}/{path:path}", _handle_file_get, methods=["GET"]),
    Route("/files/{crew_id}/{path:path}", _handle_file_put, methods=["POST"]),
]
