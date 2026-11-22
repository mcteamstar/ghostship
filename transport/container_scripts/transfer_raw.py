#!/usr/bin/env python3
"""Confined raw, archive, and git-bundle uploads for a crew workspace."""
from __future__ import annotations

import os
import errno
import secrets
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile

from transfer_paths import (
    UnsafeTransferPath,
    atomic_write,
    open_dir_chain,
    open_regular_file,
    open_workspace,
    preflight_path,
    relative_parts,
    remove_entry_at,
    remove_tree,
    rename_exchange,
    rename_noreplace,
)


class TransferBudgetExceeded(ValueError):
    """An upload exceeded an operator-configured output/storage budget."""


# tarfile consumes extended headers before yielding a member to the caller.
_ARCHIVE_METADATA_BYTES = 4 * 1024 * 1024
_ARCHIVE_METADATA_READ_BYTES = 64 * 1024
_ARCHIVE_METADATA_DEPTH = 16
_ARCHIVE_EXTENSION_TYPES = {
    tarfile.XHDTYPE, tarfile.XGLTYPE, tarfile.SOLARIS_XHDTYPE,
    tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_LONGLINK, tarfile.GNUTYPE_SPARSE,
}


class _ArchiveMetadataReader:
    def __init__(self, source) -> None:
        self.source = source
        self.remaining = _ARCHIVE_METADATA_BYTES
        self.depth = 0

    def read(self, size: int) -> bytes:
        if not 0 <= size <= min(self.remaining, _ARCHIVE_METADATA_READ_BYTES):
            raise TransferBudgetExceeded("archive extended metadata exceeds its byte limit")
        data = self.source.read(size)
        self.remaining -= len(data)
        return data

    def __getattr__(self, name: str):
        return getattr(self.source, name)


class _BoundedTarInfo(tarfile.TarInfo):
    def _proc_member(self, archive):
        if self.type not in _ARCHIVE_EXTENSION_TYPES:
            return super()._proc_member(archive)
        previous = archive.fileobj
        reader = getattr(archive, "_transfer_metadata_reader", None)
        if reader is None:
            reader = archive._transfer_metadata_reader = _ArchiveMetadataReader(previous)
        if reader.depth >= _ARCHIVE_METADATA_DEPTH:
            raise TransferBudgetExceeded("archive extended headers are nested too deeply")
        reader.depth += 1
        archive.fileobj = reader
        try:
            return super()._proc_member(archive)
        finally:
            archive.fileobj = previous
            reader.depth -= 1


def _archive_entries(
    archive: tarfile.TarFile,
    max_members: int,
    max_output_bytes: int,
) -> list[tuple[tarfile.TarInfo, list[str], str]]:
    """Validate every member name and type before extracting any member."""
    if max_members <= 0 or max_output_bytes <= 0:
        raise ValueError("archive budgets must be positive")
    entries: list[tuple[tarfile.TarInfo, list[str], str]] = []
    kinds: dict[tuple[str, ...], str] = {}
    output_bytes = 0
    for member_count, member in enumerate(archive, start=1):
        if member_count > max_members:
            raise TransferBudgetExceeded(
                f"archive exceeds the {max_members}-member limit"
            )
        # The parser has already applied these fields to the member.
        member.pax_headers = {}
        if member.name.startswith("/"):
            raise UnsafeTransferPath(f"Archive member is absolute: {member.name!r}")
        parts = [part for part in member.name.split("/") if part not in ("", ".")]
        if any(part == ".." for part in parts):
            raise UnsafeTransferPath(f"Archive member escapes destination: {member.name!r}")
        if member.isdir():
            kind = "directory"
        elif member.isfile():
            kind = "file"
        else:
            raise UnsafeTransferPath(f"Unsupported archive member type: {member.name!r}")
        if kind == "file":
            if member.size < 0:
                raise ValueError(f"Archive member has a negative size: {member.name!r}")
            output_bytes += member.size
            if output_bytes > max_output_bytes:
                raise TransferBudgetExceeded(
                    f"archive output exceeds the {max_output_bytes}-byte limit"
                )
        if not parts and kind != "directory":
            raise UnsafeTransferPath("Archive root member must be a directory")
        if parts:
            key = tuple(parts)
            previous = kinds.get(key)
            if previous is not None and previous != kind:
                raise UnsafeTransferPath(f"Conflicting archive member types: {member.name!r}")
            kinds[key] = kind
        entries.append((member, parts, kind))

    for path, kind in kinds.items():
        for depth in range(1, len(path)):
            parent_kind = kinds.get(path[:depth])
            if parent_kind is not None and parent_kind != "directory":
                raise UnsafeTransferPath(f"Archive file used as a directory: {'/'.join(path[:depth])!r}")
    return entries


class _ArchiveBudgetReader:
    """Count decompressed member data while it is copied to staging."""

    def __init__(self, source, total: list[int], limit: int) -> None:
        self._source = source
        self._total = total
        self._limit = limit
        self.count = 0

    def read(self, size: int = -1) -> bytes:
        chunk = self._source.read(size)
        if chunk:
            self.count += len(chunk)
            self._total[0] += len(chunk)
            if self._total[0] > self._limit:
                raise TransferBudgetExceeded(
                    f"archive output exceeds the {self._limit}-byte limit"
                )
        return chunk


def _stage_archive(
    root_fd: int,
    source_fd: int,
    stage_parts: list[str],
    destination_parts: list[str],
    max_members: int,
    max_output_bytes: int,
):
    """Validate and fully stage archive contents before destination mutation."""
    with os.fdopen(os.dup(source_fd), "rb") as source:
        with tarfile.open(fileobj=source, mode="r:*", tarinfo=_BoundedTarInfo) as archive:
            entries = _archive_entries(archive, max_members, max_output_bytes)
            preflight_path(root_fd, destination_parts, "directory")
            for _, member_parts, kind in entries:
                if member_parts:
                    preflight_path(root_fd, destination_parts + member_parts, kind)

            stage_fd = open_dir_chain(root_fd, stage_parts)
            extraction_name = f".unpack-{secrets.token_hex(12)}"
            actual_output_bytes = [0]
            try:
                os.mkdir(extraction_name, 0o700, dir_fd=stage_fd)
                extraction_fd = open_dir_chain(stage_fd, [extraction_name])
                try:
                    for member, member_parts, kind in entries:
                        if not member_parts:
                            continue
                        if kind == "directory":
                            directory_fd = open_dir_chain(extraction_fd, member_parts, create=True)
                            os.close(directory_fd)
                            continue
                        extracted = archive.extractfile(member)
                        if extracted is None:
                            raise ValueError(f"Could not read archive member: {member.name!r}")
                        with extracted:
                            budget_reader = _ArchiveBudgetReader(
                                extracted, actual_output_bytes, max_output_bytes
                            )
                            atomic_write(
                                extraction_fd,
                                member_parts,
                                budget_reader,
                                member.mode & 0o777,
                            )
                            if budget_reader.count != member.size:
                                raise ValueError(
                                    f"Archive member ended early: {member.name!r}"
                                )
                finally:
                    os.close(extraction_fd)
            finally:
                os.close(stage_fd)
    return extraction_name, entries


def _apply_archive(root_fd: int, stage_parts: list[str], extraction_name: str,
                   destination_parts: list[str], entries) -> None:
    """Merge fully validated staged members into the destination via dirfds."""
    destination_fd = open_dir_chain(root_fd, destination_parts, create=True)
    os.close(destination_fd)

    directory_modes: dict[tuple[str, ...], int] = {}
    file_members: dict[tuple[str, ...], tarfile.TarInfo] = {}
    for member, parts, kind in entries:
        if not parts:
            continue
        key = tuple(parts)
        if kind == "directory":
            directory_modes[key] = member.mode & 0o777
        else:
            file_members[key] = member

    for path in directory_modes:
        directory_fd = open_dir_chain(root_fd, destination_parts + list(path), create=True)
        os.close(directory_fd)

    for path in file_members:
        staged_parent = open_dir_chain(root_fd, stage_parts + [extraction_name] + list(path[:-1]))
        destination_parent = open_dir_chain(root_fd, destination_parts + list(path[:-1]), create=True)
        try:
            os.replace(path[-1], path[-1], src_dir_fd=staged_parent, dst_dir_fd=destination_parent)
        finally:
            os.close(staged_parent)
            os.close(destination_parent)

    for path, mode in sorted(directory_modes.items(), key=lambda item: len(item[0]), reverse=True):
        directory_fd = open_dir_chain(root_fd, destination_parts + list(path))
        try:
            os.fchmod(directory_fd, mode)
        finally:
            os.close(directory_fd)


def _run_git(
    args: list[str],
    cwd_fd: int,
    source_fd: int | None = None,
    check: bool = True,
    env: dict[str, str] | None = None,
):
    pass_fds = (cwd_fd,) if source_fd is None else (cwd_fd, source_fd)
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    completed = subprocess.run(
        ["git", *args],
        cwd=f"/proc/self/fd/{cwd_fd}",
        pass_fds=pass_fds,
        check=False,
        capture_output=True,
        text=True,
        env=run_env,
    )
    if check and completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
        raise RuntimeError(detail)
    return completed


def _bundle_storage_capacity(storage_root: str, configured_limit_bytes: int) -> int:
    """Return the confirmed tmpfs capacity, failing closed without a bounded mount."""
    if configured_limit_bytes <= 0:
        raise RuntimeError("bundle storage limit must be positive")
    try:
        root = os.path.realpath(storage_root)
        stat = os.statvfs(root)
        block_size = stat.f_frsize or stat.f_bsize
        capacity = stat.f_blocks * block_size
    except OSError as exc:
        raise RuntimeError("bounded bundle storage is unavailable") from exc
    if not os.path.isdir(root) or capacity <= 0 or capacity > configured_limit_bytes:
        raise RuntimeError("bounded bundle storage is unavailable")

    # Crew containers run Linux under Podman on both supported host platforms.
    # Confirm that this exact path is a tmpfs mount; statvfs alone cannot prove
    # that an ordinary, unbounded workspace directory was supplied.
    try:
        with open("/proc/self/mountinfo", encoding="utf-8") as mounts:
            for line in mounts:
                before, separator, after = line.partition(" - ")
                if not separator:
                    continue
                fields = before.split()
                filesystem = after.split()
                if len(fields) < 5 or not filesystem:
                    continue
                mountpoint = fields[4].replace("\\040", " ").replace("\\011", "\t")
                if mountpoint == root and filesystem[0] == "tmpfs":
                    return capacity
    except OSError as exc:
        raise RuntimeError("cannot verify bounded bundle storage mount") from exc
    raise RuntimeError("bounded bundle storage is unavailable")


def _copy_bundle_checkout(source: str, destination: str) -> None:
    """Copy Git checkout data while retaining the workspace's mount labels."""
    with os.scandir(source) as entries:
        for entry in entries:
            target = os.path.join(destination, entry.name)
            if entry.is_symlink():
                os.symlink(os.readlink(entry.path), target)
            elif entry.is_dir(follow_symlinks=False):
                os.mkdir(target, stat.S_IMODE(entry.stat(follow_symlinks=False).st_mode))
                _copy_bundle_checkout(entry.path, target)
            else:
                shutil.copy(entry.path, target)


def _transfer_bundle(root_fd: int, source_fd: int, destination_parts: list[str],
                     force: bool, destination: str, storage_root: str,
                     storage_capacity: int) -> str:
    if not destination_parts:
        raise UnsafeTransferPath("A bundle must be cloned below the workspace root")
    existing = preflight_path(root_fd, destination_parts, "any")
    if existing is not None and not force:
        if not stat.S_ISDIR(existing.st_mode):
            raise FileExistsError("Bundle destination exists and is not an empty directory")
        existing_fd = open_dir_chain(root_fd, destination_parts)
        try:
            if os.listdir(existing_fd):
                raise FileExistsError("Bundle destination exists and is not empty")
        finally:
            os.close(existing_fd)

    parent_fd = open_dir_chain(root_fd, destination_parts[:-1], create=True)
    destination_name = destination_parts[-1]
    clone_name = f".kirocrew-clone-{secrets.token_hex(12)}"
    clone_installed = False
    clone_identity: tuple[int, int] | None = None

    def run_bounded_git(args: list[str], cwd_fd: int, check: bool = True):
        try:
            return _run_git(
                args,
                cwd_fd,
                check=check,
                env={"TMPDIR": storage_root},
            )
        except RuntimeError as exc:
            detail = str(exc).lower()
            if "no space left on device" in detail or "disk quota exceeded" in detail:
                raise TransferBudgetExceeded(
                    f"bundle Git storage exceeds the {storage_capacity}-byte limit"
                ) from exc
            raise

    git_clone_dir: str | None = None
    bundle_input_path: str | None = None
    try:
        try:
            bundle_fd, bundle_input_path = tempfile.mkstemp(
                prefix="ga-bundle-input-", suffix=".bundle", dir=storage_root
            )
            with os.fdopen(bundle_fd, "wb") as bundle_input:
                os.lseek(source_fd, 0, os.SEEK_SET)
                with os.fdopen(os.dup(source_fd), "rb") as source:
                    shutil.copyfileobj(source, bundle_input, length=1024 * 1024)
        except OSError as exc:
            if exc.errno == errno.ENOSPC:
                raise TransferBudgetExceeded(
                    f"bundle Git storage exceeds the {storage_capacity}-byte limit"
                ) from exc
            raise
        try:
            git_clone_dir = tempfile.mkdtemp(prefix="ga-bundle-", dir=storage_root)
        except OSError as exc:
            if exc.errno == errno.ENOSPC:
                raise TransferBudgetExceeded(
                    f"bundle Git storage exceeds the {storage_capacity}-byte limit"
                ) from exc
            raise
        current = preflight_path(root_fd, destination_parts, "any")
        if (existing is None) != (current is None):
            raise UnsafeTransferPath("Bundle destination changed during validation")
        if existing is not None and current is not None:
            if (existing.st_dev, existing.st_ino) != (current.st_dev, current.st_ino):
                raise UnsafeTransferPath("Bundle destination changed during validation")
        clone_fd = os.open(
            git_clone_dir,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
        )
        try:
            clone = run_bounded_git(
                ["clone", bundle_input_path, "."], clone_fd
            )

            head = run_bounded_git(["rev-parse", "HEAD"], clone_fd, check=False)
            if head.returncode:
                branches = run_bounded_git(["branch", "-r"], clone_fd)
                branch = ""
                for line in branches.stdout.splitlines():
                    stripped = line.strip()
                    if stripped and "HEAD" not in stripped:
                        branch = stripped.removeprefix("origin/").strip()
                        break
                if branch:
                    run_bounded_git(
                        ["checkout", "-b", branch, f"origin/{branch}"], clone_fd
                    )
        finally:
            os.close(clone_fd)

        os.mkdir(clone_name, 0o700, dir_fd=parent_fd)
        staged_fd = open_dir_chain(root_fd, destination_parts[:-1] + [clone_name])
        try:
            _copy_bundle_checkout(git_clone_dir, f"/proc/self/fd/{staged_fd}")
            staged_stat = os.fstat(staged_fd)
            clone_identity = (staged_stat.st_dev, staged_stat.st_ino)
        finally:
            os.close(staged_fd)

        staged_clone = os.stat(clone_name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(staged_clone.st_mode) or clone_identity != (staged_clone.st_dev, staged_clone.st_ino):
            raise UnsafeTransferPath("Staged clone changed during upload")

        if existing is not None:
            latest = preflight_path(root_fd, destination_parts, "any")
            if latest is None or (latest.st_dev, latest.st_ino) != (existing.st_dev, existing.st_ino):
                raise UnsafeTransferPath("Bundle destination changed during clone")
            if not force:
                existing_fd = open_dir_chain(root_fd, destination_parts)
                try:
                    if os.listdir(existing_fd):
                        raise FileExistsError("Bundle destination is no longer empty")
                finally:
                    os.close(existing_fd)
            rename_exchange(parent_fd, clone_name, parent_fd, destination_name)
            moved = os.stat(clone_name, dir_fd=parent_fd, follow_symlinks=False)
            if (moved.st_dev, moved.st_ino) != (existing.st_dev, existing.st_ino):
                rename_exchange(parent_fd, clone_name, parent_fd, destination_name)
                raise UnsafeTransferPath("Bundle destination changed during replacement")
            installed = os.stat(destination_name, dir_fd=parent_fd, follow_symlinks=False)
            if (installed.st_dev, installed.st_ino) != clone_identity:
                rename_exchange(parent_fd, clone_name, parent_fd, destination_name)
                raise UnsafeTransferPath("Staged clone changed during replacement")
            if not force:
                previous_fd = open_dir_chain(root_fd, destination_parts[:-1] + [clone_name])
                try:
                    if os.listdir(previous_fd):
                        rename_exchange(parent_fd, clone_name, parent_fd, destination_name)
                        raise FileExistsError("Bundle destination is no longer empty")
                finally:
                    os.close(previous_fd)
            clone_installed = True
            remove_entry_at(parent_fd, clone_name)
        else:
            rename_noreplace(parent_fd, clone_name, parent_fd, destination_name)
            installed = os.stat(destination_name, dir_fd=parent_fd, follow_symlinks=False)
            if (installed.st_dev, installed.st_ino) != clone_identity:
                rename_noreplace(parent_fd, destination_name, parent_fd, clone_name)
                raise UnsafeTransferPath("Staged clone changed during installation")
            clone_installed = True
        return clone.stdout.strip() or f"cloned to {destination}"
    finally:
        if not clone_installed:
            try:
                remove_entry_at(parent_fd, clone_name)
            except FileNotFoundError:
                pass
        if git_clone_dir is not None:
            shutil.rmtree(git_clone_dir, ignore_errors=True)
        if bundle_input_path is not None:
            try:
                os.unlink(bundle_input_path)
            except FileNotFoundError:
                pass
        os.close(parent_fd)


def transfer(source: str, destination: str, stage: str, unpack: bool, workspace: str,
             bundle: bool = False, force: bool = False,
             max_archive_bytes: int = 1_073_741_824,
             max_archive_members: int = 100_000,
             bundle_storage_root: str | None = None,
             bundle_storage_limit_bytes: int | None = None) -> str:
    """Apply one staged upload inside the workspace and always clean its stage."""
    root_fd = open_workspace(workspace)
    operation_failed = False
    try:
        source_parts = relative_parts(workspace, source)
        stage_parts = relative_parts(workspace, stage)
        destination_parts = relative_parts(workspace, destination)
        if not stage_parts or source_parts[:-1] != stage_parts:
            raise UnsafeTransferPath("Transfer source must be inside its staging directory")
        if unpack and bundle:
            raise ValueError("unpack and bundle cannot both be enabled")
        source_fd = open_regular_file(root_fd, source_parts)
        try:
            if bundle:
                if not bundle_storage_root or bundle_storage_limit_bytes is None:
                    raise RuntimeError("bounded bundle storage configuration is unavailable")
                capacity = _bundle_storage_capacity(
                    bundle_storage_root, bundle_storage_limit_bytes
                )
                return _transfer_bundle(
                    root_fd,
                    source_fd,
                    destination_parts,
                    force,
                    destination,
                    bundle_storage_root,
                    capacity,
                )
            if unpack:
                extraction_name, entries = _stage_archive(
                    root_fd,
                    source_fd,
                    stage_parts,
                    destination_parts,
                    max_archive_members,
                    max_archive_bytes,
                )
                _apply_archive(root_fd, stage_parts, extraction_name, destination_parts, entries)
                return f"unpacked to {destination}"
            preflight_path(root_fd, destination_parts, "file")
            size = os.fstat(source_fd).st_size
            with os.fdopen(os.dup(source_fd), "rb") as upload:
                atomic_write(root_fd, destination_parts, upload)
            return f"wrote {size} bytes to {destination}"
        finally:
            os.close(source_fd)
    except BaseException:
        operation_failed = True
        raise
    finally:
        try:
            remove_tree(root_fd, workspace, stage)
        except Exception:
            if not operation_failed:
                raise
        finally:
            os.close(root_fd)


def main(argv: list[str]) -> int:
    if argv[1:] == ["--verify-bundle-storage"]:
        configured_limit = int(os.environ["GA_TRANSFER_BUNDLE_STORAGE_LIMIT_BYTES"])
        storage_root = os.environ["GA_TRANSFER_BUNDLE_STORAGE_ROOT"]
        capacity = _bundle_storage_capacity(storage_root, configured_limit)
        print(f"bundle-storage-ready:{capacity}")
        return 0
    try:
        result = transfer(
            os.environ["GA_TRANSFER_SOURCE"],
            os.environ["GA_TRANSFER_DEST"],
            os.environ["GA_TRANSFER_STAGE"],
            "--unpack" in argv[1:],
            os.environ["GA_TRANSFER_WORKSPACE"],
            bundle="--bundle" in argv[1:],
            force="--force" in argv[1:],
            max_archive_bytes=int(os.environ["GA_TRANSFER_MAX_ARCHIVE_BYTES"]),
            max_archive_members=int(os.environ["GA_TRANSFER_MAX_ARCHIVE_MEMBERS"]),
            bundle_storage_root=os.environ.get("GA_TRANSFER_BUNDLE_STORAGE_ROOT"),
            bundle_storage_limit_bytes=int(
                os.environ["GA_TRANSFER_BUNDLE_STORAGE_LIMIT_BYTES"]
            ),
        )
    except TransferBudgetExceeded as exc:
        print(f"TRANSFER_BUDGET_EXCEEDED: {exc}", file=sys.stderr)
        return 3
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
