"""Installer checks for the Radar bundle build (TRN-371, task 1.3).

``_build_images`` runs for ``./install.sh`` and for ``ghostship upgrade`` (which execs
``bin/install.sh``). These tests drive it with an in-process fake Podman CLI that
records each call and scripts the outcome of every build, so the failure message and
the rule that the running image survives a failed build are checked without running
any Podman binary.
"""
from __future__ import annotations

import importlib
import io
import subprocess
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Sentinel command name. It is never executed: FakePodman intercepts every call that
# starts with it, and every other subprocess call is passed to the real module.
FAKE_PODMAN = ["fake-podman"]


class _FakeProcess:
    """Stands in for the Popen handle used to stream the ga-radar build output."""

    def __init__(self, lines: list[str], returncode: int) -> None:
        self.stdout = io.StringIO("".join(line + "\n" for line in lines))
        self._returncode = returncode

    def wait(self) -> int:
        return self._returncode


class FakePodman:
    """Scripts podman's answers for the installer's image-build steps."""

    def __init__(self, *, radar_returncode: int = 0, radar_lines: list[str] | None = None) -> None:
        self.calls: list[str] = []
        self._radar_returncode = radar_returncode
        self._radar_lines = radar_lines if radar_lines is not None else [
            "STEP 2/12: RUN npm ci --ignore-scripts --no-audit --no-fund",
            "npm error code ENOTFOUND",
        ]

    def _respond(self, cmd: list[str]) -> tuple[int, list[str]]:
        args = cmd[len(FAKE_PODMAN):]
        self.calls.append(" ".join(args))
        if args[:2] == ["image", "exists"]:
            return 1, []  # no image cached: no stale-image detection
        if "localhost/ga-radar:latest" in args:
            if self._radar_returncode == 0:
                return 0, ["STEP 12/12: CMD [\"uvicorn\", \"server:app\"]"]
            return self._radar_returncode, self._radar_lines
        return 0, []

    @staticmethod
    def _owns(cmd) -> bool:
        return isinstance(cmd, list) and cmd[: len(FAKE_PODMAN)] == FAKE_PODMAN

    def make_subprocess_namespace(self) -> types.SimpleNamespace:
        real = subprocess

        def run(cmd, *args, check: bool = False, **kwargs):
            if not self._owns(cmd):
                return real.run(cmd, *args, check=check, **kwargs)
            returncode, _lines = self._respond(cmd)
            if check and returncode != 0:
                raise real.CalledProcessError(returncode, cmd)
            return real.CompletedProcess(cmd, returncode, stdout="", stderr="")

        def popen(cmd, *args, **kwargs):
            if not self._owns(cmd):
                return real.Popen(cmd, *args, **kwargs)
            returncode, lines = self._respond(cmd)
            return _FakeProcess(lines, returncode)

        return types.SimpleNamespace(
            run=run,
            Popen=popen,
            PIPE=real.PIPE,
            STDOUT=real.STDOUT,
            CalledProcessError=real.CalledProcessError,
            CompletedProcess=real.CompletedProcess,
        )


@pytest.fixture
def install_main(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(REPO_ROOT / "bin" / "lib"))
    return importlib.import_module("install_main")


@pytest.fixture
def podman_for(install_main, monkeypatch: pytest.MonkeyPatch):
    """Install a FakePodman into the installer module and return it."""

    def install(fake: FakePodman) -> FakePodman:
        monkeypatch.setattr(install_main, "subprocess", fake.make_subprocess_namespace())
        return fake

    return install


def _build(install_main) -> None:
    install_main._build_images(
        str(REPO_ROOT),
        FAKE_PODMAN,
        agent_toolchains="",
        agents_ref="",
        kc_base_image="",
        version="0.0.0-test",
    )


class TestRadarBundleBuildCommand:

    def test_ga_radar_is_built_from_the_radar_context(self, install_main, podman_for) -> None:
        fake = podman_for(FakePodman())
        _build(install_main)
        radar_builds = [c for c in fake.calls if "localhost/ga-radar:latest" in c]
        assert radar_builds == [f"build -t localhost/ga-radar:latest {REPO_ROOT / 'radar'}"]

    def test_successful_build_reports_the_image(self, install_main, podman_for, capsys) -> None:
        podman_for(FakePodman())
        _build(install_main)
        out = capsys.readouterr().out
        assert "Building localhost/ga-radar:latest ..." in out
        assert "✓ ga-radar image built" in out

    def test_radar_is_built_last_so_transport_is_already_current(self, install_main, podman_for) -> None:
        fake = podman_for(FakePodman())
        _build(install_main)
        builds = [c for c in fake.calls if c.startswith("build ")]
        assert "localhost/ga-radar:latest" in builds[-1]


class TestRadarBundleBuildFailure:

    def test_failed_build_stops_with_a_radar_specific_message(
        self, install_main, podman_for, capsys,
    ) -> None:
        podman_for(FakePodman(radar_returncode=125))
        with pytest.raises(SystemExit) as exc:
            _build(install_main)
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "Radar bundle build failed" in err
        assert "STEP 2/12: RUN npm ci --ignore-scripts --no-audit --no-fund" in err
        assert "npm registry is reachable" in err
        assert "localhost/ga-radar:latest image was left in place" in err

    def test_failed_build_streams_the_podman_output(self, install_main, podman_for, capsys) -> None:
        podman_for(FakePodman(radar_returncode=125))
        with pytest.raises(SystemExit):
            _build(install_main)
        assert "npm error code ENOTFOUND" in capsys.readouterr().out

    def test_failed_build_never_removes_or_retags_the_running_image(
        self, install_main, podman_for,
    ) -> None:
        fake = podman_for(FakePodman(radar_returncode=125))
        with pytest.raises(SystemExit):
            _build(install_main)
        touching_radar = [c for c in fake.calls if "ga-radar" in c]
        assert touching_radar == [f"build -t localhost/ga-radar:latest {REPO_ROOT / 'radar'}"]
        assert not [c for c in fake.calls if c.split()[0] in {"rmi", "rm", "tag"}]

    def test_failure_before_any_step_is_still_reported(self, install_main, podman_for, capsys) -> None:
        podman_for(FakePodman(radar_returncode=2, radar_lines=[]))
        with pytest.raises(SystemExit):
            _build(install_main)
        err = capsys.readouterr().err
        assert "Radar bundle build failed before its first build step" in err
        assert "left in place" in err

    def test_typecheck_or_build_failure_points_at_the_frontend_source(
        self, install_main, podman_for, capsys,
    ) -> None:
        podman_for(FakePodman(
            radar_returncode=1,
            radar_lines=["STEP 9/12: RUN npm run typecheck && npm run build"],
        ))
        with pytest.raises(SystemExit):
            _build(install_main)
        assert "Fix radar/web, then retry." in capsys.readouterr().err
