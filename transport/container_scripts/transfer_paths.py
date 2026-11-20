"""Descriptor-relative filesystem helpers for confined crew uploads."""
from __future__ import annotations

import errno
import os
import secrets
import shutil
import stat


class UnsafeTransferPath(ValueError):
    """Raised when an upload path cannot be confined to the workspace."""


_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def relative_parts(workspace: str, path: str) -> list[str]:
    """Return a lexical workspace-relative path, rejecting boundary escapes."""
    root = os.path.normpath(os.path.abspath(workspace))
    candidate = os.path.normpath(os.path.abspath(path))
    try:
        if os.path.commonpath((root, candidate)) != root:
            raise UnsafeTransferPath(f"Path escapes workspace root: {path!r}")
    except ValueError as exc:
        raise UnsafeTransferPath(f"Path escapes workspace root: {path!r}") from exc
    relative = os.path.relpath(candidate, root)
    if relative == ".":
        return []
    parts = relative.split(os.sep)
    if any(part in ("", ".", "..") for part in parts):
        raise UnsafeTransferPath(f"Unsafe workspace path: {path!r}")
    return parts


def open_workspace(workspace: str) -> int:
    """Open the configured workspace root as a pinned directory descriptor."""
    root = os.path.realpath(workspace)
    return os.open(root, _DIR_FLAGS | _NOFOLLOW)


def _open_dir_at(parent_fd: int, name: str, create: bool = False) -> int:
    try:
        return os.open(name, _DIR_FLAGS | _NOFOLLOW, dir_fd=parent_fd)
    except FileNotFoundError:
        if not create:
            raise
        try:
            os.mkdir(name, 0o755, dir_fd=parent_fd)
        except FileExistsError:
            pass
        try:
            return os.open(name, _DIR_FLAGS | _NOFOLLOW, dir_fd=parent_fd)
        except OSError as exc:
            raise UnsafeTransferPath(f"Unsafe directory component: {name!r}") from exc
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise UnsafeTransferPath(f"Unsafe directory component: {name!r}") from exc
        raise


def open_dir_chain(root_fd: int, parts: list[str], create: bool = False) -> int:
    """Open a workspace-relative directory chain without following symlinks."""
    current_fd = os.dup(root_fd)
    try:
        for part in parts:
            next_fd = _open_dir_at(current_fd, part, create=create)
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except Exception:
        os.close(current_fd)
        raise


def _existing_dir_chain(root_fd: int, parts: list[str]) -> int | None:
    """Open an existing directory chain, returning None at the first absence."""
    current_fd = os.dup(root_fd)
    try:
        for part in parts:
            try:
                before = os.stat(part, dir_fd=current_fd, follow_symlinks=False)
            except FileNotFoundError:
                os.close(current_fd)
                return None
            if not stat.S_ISDIR(before.st_mode):
                raise UnsafeTransferPath(f"Unsafe directory component: {part!r}")
            next_fd = _open_dir_at(current_fd, part)
            opened = os.fstat(next_fd)
            if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                os.close(next_fd)
                raise UnsafeTransferPath(f"Path changed during validation: {part!r}")
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except Exception:
        os.close(current_fd)
        raise


def _entry_stat(parent_fd: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def preflight_path(root_fd: int, parts: list[str], kind: str) -> os.stat_result | None:
    """Reject symlinks and incompatible existing entries before any writes."""
    if kind not in {"file", "directory", "any"}:
        raise ValueError(f"Unknown path kind: {kind}")
    if not parts:
        if kind != "directory":
            raise UnsafeTransferPath("The workspace root cannot be a file destination")
        return os.fstat(root_fd)
    parent_fd = _existing_dir_chain(root_fd, parts[:-1])
    if parent_fd is None:
        return None
    try:
        entry = _entry_stat(parent_fd, parts[-1])
        if entry is None:
            return None
        if stat.S_ISLNK(entry.st_mode):
            raise UnsafeTransferPath(f"Symlink destination is not allowed: {parts[-1]!r}")
        if kind == "file" and not stat.S_ISREG(entry.st_mode):
            raise UnsafeTransferPath(f"Destination is not a regular file: {parts[-1]!r}")
        if kind == "directory" and not stat.S_ISDIR(entry.st_mode):
            raise UnsafeTransferPath(f"Destination is not a directory: {parts[-1]!r}")
        if kind == "any" and not (stat.S_ISREG(entry.st_mode) or stat.S_ISDIR(entry.st_mode)):
            raise UnsafeTransferPath(f"Unsupported destination type: {parts[-1]!r}")
        return entry
    finally:
        os.close(parent_fd)


def open_regular_file(root_fd: int, parts: list[str]) -> int:
    """Open a regular file through no-follow directory descriptors."""
    if not parts:
        raise UnsafeTransferPath("A file path is required")
    parent_fd = open_dir_chain(root_fd, parts[:-1])
    try:
        try:
            fd = os.open(parts[-1], os.O_RDONLY | _NOFOLLOW | getattr(os, "O_CLOEXEC", 0), dir_fd=parent_fd)
        except OSError as exc:
            raise UnsafeTransferPath(f"Cannot safely open transfer file: {parts[-1]!r}") from exc
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise UnsafeTransferPath(f"Transfer source is not a regular file: {parts[-1]!r}")
        return fd
    finally:
        os.close(parent_fd)


def atomic_write(root_fd: int, parts: list[str], source, mode: int | None = None) -> None:
    """Write a file through a sibling temp file and atomically replace its leaf."""
    if not parts:
        raise UnsafeTransferPath("A file path is required")
    parent_fd = open_dir_chain(root_fd, parts[:-1], create=True)
    temporary = f".kirocrew-write-{secrets.token_hex(12)}"
    temp_fd = -1
    temp_created = False
    try:
        existing = _entry_stat(parent_fd, parts[-1])
        if existing is not None:
            if stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode):
                raise UnsafeTransferPath(f"Unsafe file destination: {parts[-1]!r}")
        final_mode = mode
        if final_mode is None:
            final_mode = (existing.st_mode & 0o777) if existing is not None else 0o666
        temp_fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=parent_fd,
        )
        temp_created = True
        with os.fdopen(temp_fd, "wb") as output:
            temp_fd = -1
            shutil.copyfileobj(source, output, length=1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
            os.fchmod(output.fileno(), final_mode & 0o777)
        os.replace(temporary, parts[-1], src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
    finally:
        if temp_fd >= 0:
            os.close(temp_fd)
        if temp_created:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        os.close(parent_fd)


def remove_entry_at(parent_fd: int, name: str) -> None:
    """Remove one entry without following symlinks encountered in its tree."""
    entry = _entry_stat(parent_fd, name)
    if entry is None:
        return
    if not stat.S_ISDIR(entry.st_mode):
        os.unlink(name, dir_fd=parent_fd)
        return
    child_fd = _open_dir_at(parent_fd, name)
    try:
        opened = os.fstat(child_fd)
        if (entry.st_dev, entry.st_ino) != (opened.st_dev, opened.st_ino):
            raise UnsafeTransferPath(f"Path changed during cleanup: {name!r}")
        for child in os.listdir(child_fd):
            remove_entry_at(child_fd, child)
    finally:
        os.close(child_fd)
    os.rmdir(name, dir_fd=parent_fd)


def remove_tree(root_fd: int, workspace: str, path: str) -> None:
    """Remove a workspace-contained staging tree without following links."""
    parts = relative_parts(workspace, path)
    if not parts:
        raise UnsafeTransferPath("The workspace root cannot be removed")
    parent_fd = _existing_dir_chain(root_fd, parts[:-1])
    if parent_fd is None:
        return
    try:
        remove_entry_at(parent_fd, parts[-1])
    finally:
        os.close(parent_fd)


def rename_noreplace(src_dir_fd: int, src: str, dst_dir_fd: int, dst: str) -> None:
    """Atomically rename an entry only when the destination does not exist."""
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise OSError(errno.ENOTSUP, "renameat2 is required for safe bundle installation")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        src_dir_fd,
        os.fsencode(src),
        dst_dir_fd,
        os.fsencode(dst),
        1,  # RENAME_NOREPLACE
    )
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), dst)


def rename_exchange(left_dir_fd: int, left: str, right_dir_fd: int, right: str) -> None:
    """Atomically exchange two entries without opening either path by name."""
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise OSError(errno.ENOTSUP, "renameat2 is required for safe bundle replacement")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        left_dir_fd,
        os.fsencode(left),
        right_dir_fd,
        os.fsencode(right),
        2,  # RENAME_EXCHANGE
    )
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), right)
