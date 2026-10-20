"""Unit tests for AcademyLoader skill delivery."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path
from unittest.mock import patch

from tests.fakes import FakePodmanClient


class _CapturePodman(FakePodmanClient):
    def __init__(self) -> None:
        super().__init__()
        self.archives: list[tuple[str, str, bytes]] = []

    def container_archive_put(self, name: str, workspace_path: str, tar_body: bytes) -> None:
        self.archives.append((name, workspace_path, tar_body))
        super().container_archive_put(name, workspace_path, tar_body)


def _archive_members(archive: bytes) -> dict[str, tuple[bytes, int]]:
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        return {
            member.name: (tar.extractfile(member).read() if member.isfile() else b"", member.mode)
            for member in tar.getmembers()
        }


def _loader(skills_dir: Path, podman: _CapturePodman, selection: object = "*"):
    import transport.academy as academy

    with (
        patch.object(academy, "_SKILLS_DIR", skills_dir),
        patch.object(academy, "_load_crew_manifest", return_value={"skills": selection}),
    ):
        return academy.AcademyLoader(podman, "gs-test")._copy_skills()


def test_skill_script_and_skill_doc_are_copied_with_modes(tmp_path: Path) -> None:
    skill = tmp_path / "with-script"
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_text("skill\n", encoding="utf-8")
    script = skill / "scripts" / "x"
    script.write_text("#!/bin/sh\necho x\n", encoding="utf-8")
    script.chmod(0o755)

    podman = _CapturePodman()
    assert _loader(tmp_path, podman) == ["with-script"]
    assert len(podman.archives) == 1
    members = _archive_members(podman.archives[0][2])
    assert set(members) == {"SKILL.md", "scripts/x"}
    assert members["SKILL.md"][1] == 0o644
    assert members["scripts/x"][1] == 0o755


def test_skill_with_only_skill_md_keeps_single_member(tmp_path: Path) -> None:
    skill = tmp_path / "docs-only"
    skill.mkdir()
    (skill / "SKILL.md").write_text("only\n", encoding="utf-8")

    podman = _CapturePodman()
    assert _loader(tmp_path, podman) == ["docs-only"]
    assert len(podman.archives) == 1
    assert set(_archive_members(podman.archives[0][2])) == {"SKILL.md"}


def test_symlink_is_skipped(tmp_path: Path) -> None:
    skill = tmp_path / "with-link"
    skill.mkdir()
    (skill / "SKILL.md").write_text("real\n", encoding="utf-8")
    (skill / "linked").symlink_to(skill / "SKILL.md")

    podman = _CapturePodman()
    _loader(tmp_path, podman)
    assert set(_archive_members(podman.archives[0][2])) == {"SKILL.md"}


def test_manifest_filter_is_applied(tmp_path: Path) -> None:
    selected = tmp_path / "selected"
    other = tmp_path / "other"
    selected.mkdir()
    other.mkdir()
    (selected / "SKILL.md").write_text("selected\n", encoding="utf-8")
    (other / "SKILL.md").write_text("other\n", encoding="utf-8")

    podman = _CapturePodman()
    assert _loader(tmp_path, podman, ["selected"]) == ["selected"]
    assert len(podman.archives) == 1
