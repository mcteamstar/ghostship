#!/usr/bin/env python3
"""Confined raw, archive, and git-bundle uploads for a crew workspace."""
from __future__ import annotations

import os
import secrets
import stat
import subprocess
import sys
import tarfile

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


def _archive_entries(archive: tarfile.TarFile) -> list[tuple[tarfile.TarInfo, list[str], str]]:
    """Validate every member name and type before extracting any member."""
    entries: list[tuple[tarfile.TarInfo, list[str], str]] = []
    kinds: dict[tuple[str, ...], str] = {}
    for member in archive.getmembers():
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


def _stage_archive(root_fd: int, source_fd: int, stage_parts: list[str], destination_parts: list[str]):
    """Validate and fully stage archive contents before destination mutation."""
    with os.fdopen(os.dup(source_fd), "rb") as source:
        with tarfile.open(fileobj=source, mode="r:*") as archive:
            entries = _archive_entries(archive)
            preflight_path(root_fd, destination_parts, "directory")
            for _, member_parts, kind in entries:
                if member_parts:
                    preflight_path(root_fd, destination_parts + member_parts, kind)

            stage_fd = open_dir_chain(root_fd, stage_parts)
            extraction_name = f".unpack-{secrets.token_hex(12)}"
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
                            atomic_write(extraction_fd, member_parts, extracted, member.mode & 0o777)
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


def _run_git(args: list[str], cwd_fd: int, source_fd: int | None = None, check: bool = True):
    pass_fds = (cwd_fd,) if source_fd is None else (cwd_fd, source_fd)
    completed = subprocess.run(
        ["git", *args],
        cwd=f"/proc/self/fd/{cwd_fd}",
        pass_fds=pass_fds,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
        raise RuntimeError(detail)
    return completed


def _transfer_bundle(root_fd: int, source_fd: int, destination_parts: list[str],
                     force: bool, destination: str) -> str:
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
    try:
        current = preflight_path(root_fd, destination_parts, "any")
        if (existing is None) != (current is None):
            raise UnsafeTransferPath("Bundle destination changed during validation")
        if existing is not None and current is not None:
            if (existing.st_dev, existing.st_ino) != (current.st_dev, current.st_ino):
                raise UnsafeTransferPath("Bundle destination changed during validation")
        os.mkdir(clone_name, 0o700, dir_fd=parent_fd)
        clone_fd = open_dir_chain(root_fd, destination_parts[:-1] + [clone_name])
        try:
            os.lseek(source_fd, 0, os.SEEK_SET)
            clone = _run_git(["clone", f"/proc/self/fd/{source_fd}", "."], clone_fd, source_fd)

            head = _run_git(["rev-parse", "HEAD"], clone_fd, check=False)
            if head.returncode:
                branches = _run_git(["branch", "-r"], clone_fd)
                branch = ""
                for line in branches.stdout.splitlines():
                    stripped = line.strip()
                    if stripped and "HEAD" not in stripped:
                        branch = stripped.removeprefix("origin/").strip()
                        break
                if branch:
                    _run_git(["checkout", "-b", branch, f"origin/{branch}"], clone_fd)
            clone_stat = os.fstat(clone_fd)
            clone_identity = (clone_stat.st_dev, clone_stat.st_ino)
        finally:
            os.close(clone_fd)

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
        os.close(parent_fd)


def transfer(source: str, destination: str, stage: str, unpack: bool, workspace: str,
             bundle: bool = False, force: bool = False) -> str:
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
                return _transfer_bundle(root_fd, source_fd, destination_parts, force, destination)
            if unpack:
                extraction_name, entries = _stage_archive(root_fd, source_fd, stage_parts, destination_parts)
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
    result = transfer(
        os.environ["GA_TRANSFER_SOURCE"],
        os.environ["GA_TRANSFER_DEST"],
        os.environ["GA_TRANSFER_STAGE"],
        "--unpack" in argv[1:],
        os.environ["GA_TRANSFER_WORKSPACE"],
        bundle="--bundle" in argv[1:],
        force="--force" in argv[1:],
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
