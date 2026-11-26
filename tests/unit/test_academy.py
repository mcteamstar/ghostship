"""Unit tests for AcademyLoader staging and setup path (TRN-264)."""

from __future__ import annotations

import io
import json
import tarfile
import pytest
from pathlib import Path
from unittest.mock import patch

from tests.fakes import FakePodmanClient


class _CapturePodman(FakePodmanClient):
    def __init__(self) -> None:
        super().__init__()
        self.archives: list[tuple[str, str, bytes]] = []
        self.execs: list[tuple[str, list]] = []
        self.stdin_execs: list[tuple[str, list, bytes]] = []

    def container_archive_put(self, name: str, workspace_path: str, tar_body: bytes) -> None:
        self.archives.append((name, workspace_path, tar_body))
        super().container_archive_put(name, workspace_path, tar_body)

    def container_exec(self, name: str, cmd: list, env=None) -> str:
        self.execs.append((name, cmd))
        return super().container_exec(name, cmd, env)

    def container_exec_stdin(self, name, cmd, stdin_data):
        self.execs.append((name, cmd))
        self.stdin_execs.append((name, cmd, stdin_data))
        return "Done."


def _archive_members(archive: bytes) -> dict[str, tuple[bytes, int]]:
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        return {
            member.name: (tar.extractfile(member).read() if member.isfile() else b"", member.mode)
            for member in tar.getmembers()
        }


def _stage_skills_loader(skills_dir: Path, podman: _CapturePodman, selection: object = "*"):
    import transport.academy as academy

    with (
        patch.object(academy, "_SKILLS_DIR", skills_dir),
        patch.object(academy, "_load_crew_manifest", return_value={"skills": selection}),
    ):
        return academy.AcademyLoader(podman, "gs-test")._stage_skills()


# ── _stage_skills tests ───────────────────────────────────────────────────────

def test_skill_script_and_skill_doc_are_copied_with_modes(tmp_path: Path) -> None:
    skill = tmp_path / "with-script"
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_text("skill\n", encoding="utf-8")
    script = skill / "scripts" / "x"
    script.write_text("#!/bin/sh\necho x\n", encoding="utf-8")
    script.chmod(0o755)

    podman = _CapturePodman()
    assert _stage_skills_loader(tmp_path, podman) == ["with-script"]
    # one mkdir -p exec + one archive_put per skill
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
    assert _stage_skills_loader(tmp_path, podman) == ["docs-only"]
    assert len(podman.archives) == 1
    assert set(_archive_members(podman.archives[0][2])) == {"SKILL.md"}


def test_symlink_is_skipped(tmp_path: Path) -> None:
    skill = tmp_path / "with-link"
    skill.mkdir()
    (skill / "SKILL.md").write_text("real\n", encoding="utf-8")
    (skill / "linked").symlink_to(skill / "SKILL.md")

    podman = _CapturePodman()
    _stage_skills_loader(tmp_path, podman)
    assert set(_archive_members(podman.archives[0][2])) == {"SKILL.md"}


def test_manifest_filter_is_applied(tmp_path: Path) -> None:
    selected = tmp_path / "selected"
    other = tmp_path / "other"
    selected.mkdir()
    other.mkdir()
    (selected / "SKILL.md").write_text("selected\n", encoding="utf-8")
    (other / "SKILL.md").write_text("other\n", encoding="utf-8")

    podman = _CapturePodman()
    assert _stage_skills_loader(tmp_path, podman, ["selected"]) == ["selected"]
    assert len(podman.archives) == 1


def test_stage_skills_destination_is_agents_skills_dir(tmp_path: Path) -> None:
    """Skills are staged into .agents/skills/, not the old kiro path."""
    import transport.academy as academy

    skill = tmp_path / "myskill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("content\n", encoding="utf-8")

    podman = _CapturePodman()
    with (
        patch.object(academy, "_SKILLS_DIR", tmp_path),
        patch.object(academy, "_load_crew_manifest", return_value={"skills": "*"}),
    ):
        academy.AcademyLoader(podman, "gs-test")._stage_skills()

    # The archive_put destination path must be under .agents/skills/
    assert len(podman.archives) == 1
    dest_path = podman.archives[0][1]
    assert dest_path.startswith("/home/kirocrew/.agents/skills/"), (
        f"Expected .agents/skills/ prefix, got {dest_path!r}"
    )


def test_stage_skills_skips_bytecode_caches(tmp_path: Path) -> None:
    """__pycache__/ and *.pyc left by local test runs are not staged."""
    import transport.academy as academy

    skill = tmp_path / "myskill"
    (skill / "scripts" / "__pycache__").mkdir(parents=True)
    (skill / "SKILL.md").write_text("content\n", encoding="utf-8")
    (skill / "scripts" / "x").write_text("#!/bin/sh\n", encoding="utf-8")
    (skill / "scripts" / "__pycache__" / "x.cpython-313.pyc").write_bytes(b"\x00bytecode")
    (skill / "scripts" / "stray.pyc").write_bytes(b"\x00bytecode")

    podman = _CapturePodman()
    with (
        patch.object(academy, "_SKILLS_DIR", tmp_path),
        patch.object(academy, "_load_crew_manifest", return_value={"skills": "*"}),
    ):
        academy.AcademyLoader(podman, "gs-test")._stage_skills()

    members = _archive_members(podman.archives[0][2])
    assert set(members) == {"SKILL.md", "scripts/x"}


# ── _stage_steering tests ─────────────────────────────────────────────────────

def test_stage_steering_puts_files_in_agents_context(tmp_path: Path) -> None:
    """Steering docs are staged into .agents/context/ (real implementation)."""
    import transport.academy as academy

    steering_dir = tmp_path
    (steering_dir / "STANDING_ORDERS.md").write_text("orders\n", encoding="utf-8")
    (steering_dir / "TIPS.md").write_text("tips\n", encoding="utf-8")

    podman = _CapturePodman()
    loader = academy.AcademyLoader(podman, "gs-test")

    orig_path_cls = academy.Path

    class _FakePath:
        def __init__(self, *args):
            if len(args) == 1 and args[0] == "/steering":
                self._p = steering_dir
            else:
                self._p = orig_path_cls(*args)

        def __getattr__(self, name):
            return getattr(self._p, name)

    with patch.object(academy, "_load_crew_manifest", return_value={"steering": "*"}):
        with patch.object(academy, "Path", _FakePath):
            result = loader._stage_steering()

    assert sorted(result) == ["STANDING_ORDERS.md", "TIPS.md"]
    # All archive_put calls must target .agents/context/
    for _, dest, _ in podman.archives:
        assert dest == "/home/kirocrew/.agents/context", (
            f"Expected .agents/context but got {dest!r}"
        )


def test_stage_steering_destination_is_agents_context(tmp_path: Path) -> None:
    """Direct test: _stage_steering archives go to _AGENTS_CONTEXT_DIR."""
    import transport.academy as academy

    steering_dir = tmp_path
    (tmp_path / "doc.md").write_text("content\n", encoding="utf-8")

    podman = _CapturePodman()
    loader = academy.AcademyLoader(podman, "gs-test")

    # Monkey-patch the source path inside _stage_steering by overriding it
    original = academy._AGENTS_CONTEXT_DIR
    assert original == "/home/kirocrew/.agents/context"

    with patch.object(academy, "_load_crew_manifest", return_value={"steering": "*"}):
        # Patch Path("/steering") → use our tmp_path
        orig_path_cls = academy.Path

        class _FakePath:
            def __init__(self, *args):
                if len(args) == 1 and args[0] == "/steering":
                    self._p = steering_dir
                else:
                    self._p = orig_path_cls(*args)

            def __getattr__(self, name):
                return getattr(self._p, name)

        with patch.object(academy, "Path", _FakePath):
            loader._stage_steering()

    # All archive puts should target _AGENTS_CONTEXT_DIR
    for _, dest, _ in podman.archives:
        assert dest == "/home/kirocrew/.agents/context"


# ── _stage_mcp tests ──────────────────────────────────────────────────────────

def test_stage_mcp_writes_servers_json_with_disabled_false(tmp_path: Path) -> None:
    """MCP entries are written to .agents/mcp/servers.json with disabled=false."""
    import transport.academy as academy

    mcp_dir = tmp_path / "mcp"
    mcp_dir.mkdir()
    (mcp_dir / "playwright.json").write_text(
        json.dumps({"command": "npx", "args": ["playwright-mcp"]}),
        encoding="utf-8",
    )

    podman = _CapturePodman()
    loader = academy.AcademyLoader(podman, "gs-test")

    with (
        patch.object(academy, "_load_crew_manifest", return_value={
            "agents": "*", "skills": "*", "steering": "*",
            "mcpServers": ["playwright"],
        }),
        patch.object(academy, "_MCP_CATALOGUE_DIR", mcp_dir),
    ):
        loader._stage_mcp()

    # One archive should have been written to _AGENTS_MCP_DIR
    assert len(podman.archives) == 1
    dest = podman.archives[0][1]
    assert dest == "/home/kirocrew/.agents/mcp"

    members = _archive_members(podman.archives[0][2])
    assert "servers.json" in members

    servers = json.loads(members["servers.json"][0])
    assert isinstance(servers, dict)
    assert list(servers) == ["playwright"]
    entry = servers["playwright"]
    assert entry["disabled"] is False
    assert entry["command"] == "npx"


def test_spec_ops_playwright_configuration_is_delivered() -> None:
    """The real spec-ops manifest stages Playwright and Ghost receives its grant."""
    import transport.academy as academy

    repo_root = Path(__file__).resolve().parents[2]
    manifest = json.loads(
        (repo_root / "crews/spec-ops/manifest.json").read_text(encoding="utf-8")
    )
    podman = _CapturePodman()
    loader = academy.AcademyLoader(podman, "gs-spec-ops", acp_backend="codex")

    def academy_path(path: str | Path) -> Path:
        return repo_root / "academy/agents" if str(path) == "/agents" else Path(path)

    with (
        patch.object(academy, "Path", academy_path),
        patch.object(academy, "_MCP_CATALOGUE_DIR", repo_root / "academy/mcp"),
        patch.object(academy, "_load_crew_manifest", return_value=manifest),
    ):
        loader._stage_mcp()
        copied_agents = loader._copy_agents()

    assert "ghost.json" in copied_agents
    mcp_archive = next(
        _archive_members(body)
        for _, dest, body in podman.archives
        if dest == "/home/kirocrew/.agents/mcp"
    )
    servers = json.loads(mcp_archive["servers.json"][0])
    assert list(servers) == ["playwright"]
    assert servers["playwright"]["disabled"] is False
    assert servers["playwright"]["command"] == "npx"
    assert servers["playwright"]["args"] == [
        "--yes",
        "@playwright/mcp@latest",
        "--executable-path",
        "/usr/bin/chromium",
        "--headless",
        "--no-sandbox",
    ]
    assert servers["playwright"]["env"] == {"PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1"}
    assert json.loads(mcp_archive["codex.servers.json"][0]) == {
        "playwright": {"enabled": True}
    }

    delivered_agents = {}
    for _, dest, body in podman.archives:
        if dest == "/home/kirocrew/.kiro/agents":
            delivered_agents.update(_archive_members(body))
    delivered_ghost = json.loads(delivered_agents["ghost.json"][0])
    assert "@playwright" in delivered_ghost["tools"]
    assert "@playwright" in delivered_ghost["allowedTools"]
    assert delivered_ghost["mcpServers"] == {
        "playwright": {
            "type": "stdio",
            "command": "npx",
            "args": [
                "--yes",
                "@playwright/mcp@latest",
                "--executable-path",
                "/usr/bin/chromium",
                "--headless",
                "--no-sandbox",
            ],
            "env": {"PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1"},
            "disabled": False,
        }
    }
    for agent_path in (repo_root / "academy/agents").glob("*.json"):
        if agent_path.name == "ghost.json":
            continue
        agent = json.loads(agent_path.read_text(encoding="utf-8"))
        assert "@playwright" not in agent.get("tools", [])
        assert "@playwright" not in agent.get("allowedTools", [])
        if agent_path.name in delivered_agents:
            delivered = json.loads(delivered_agents[agent_path.name][0])
            assert "playwright" not in delivered.get("mcpServers", {})


def test_copy_agents_preserves_persona_mcp_entry_over_composition_entry(tmp_path: Path) -> None:
    """An agent's explicit MCP config wins over the selected composition entry."""
    import transport.academy as academy

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "ghost.json").write_text(json.dumps({
        "name": "ghost",
        "tools": ["@playwright"],
        "mcpServers": {
            "playwright": {"command": "persona-command", "args": ["own"]},
            "private": {"command": "private-command", "args": []},
        },
    }), encoding="utf-8")

    original_path = academy.Path

    def academy_path(path: str | Path) -> Path:
        return agents_dir if str(path) == "/agents" else original_path(path)

    podman = _CapturePodman()
    loader = academy.AcademyLoader(podman, "gs-persona-mcp")
    loader._staged_mcp_servers = {
        "playwright": {"command": "composition-command", "args": []},
        "nexus": {"command": "nexus-command", "args": []},
    }

    with (
        patch.object(academy, "Path", academy_path),
        patch.object(academy, "_load_crew_manifest", return_value={"agents": "*"}),
    ):
        assert loader._copy_agents() == ["ghost.json"]

    delivered = json.loads(_archive_members(podman.archives[0][2])["ghost.json"][0])
    assert delivered["mcpServers"] == {
        "playwright": {"command": "persona-command", "args": ["own"]},
        "private": {"command": "private-command", "args": []},
    }


def test_stage_mcp_skips_missing_catalogue_entry(tmp_path: Path) -> None:
    """Missing catalogue entry is skipped without error."""
    import transport.academy as academy

    podman = _CapturePodman()
    loader = academy.AcademyLoader(podman, "gs-test")

    with (
        patch.object(academy, "_load_crew_manifest", return_value={
            "mcpServers": ["nonexistent"],
        }),
        patch.object(academy, "_MCP_CATALOGUE_DIR", tmp_path),
    ):
        loader._stage_mcp()

    # No archive should have been written (empty resolved_entries)
    assert len(podman.archives) == 0


def test_stage_mcp_no_mcp_servers_key(tmp_path: Path) -> None:
    """No mcpServers in manifest means _stage_mcp is a no-op."""
    import transport.academy as academy

    podman = _CapturePodman()
    loader = academy.AcademyLoader(podman, "gs-test")

    with patch.object(academy, "_load_crew_manifest", return_value={"agents": "*"}):
        loader._stage_mcp()

    assert len(podman.archives) == 0
    assert len(podman.execs) == 0


# ── _run_setup tests ──────────────────────────────────────────────────────────

def test_run_setup_configures_selected_and_detected_harnesses() -> None:
    """Setup always configures the selected backend, then all detected ones."""
    import transport.academy as academy

    podman = _CapturePodman()
    loader = academy.AcademyLoader(podman, "gs-test", acp_backend="kiro")
    loader._run_setup()

    exec_cmds = [cmd for _, cmd in podman.execs]
    assert exec_cmds == [
        ["/home/kirocrew/.agents/setup", "kiro", "--yolo"],
        ["/home/kirocrew/.agents/setup", "--yolo"],
    ]
    assert podman.stdin_execs == [
        ("gs-test", ["/home/kirocrew/.agents/setup", "kiro", "--yolo"], b"y\ny\n"),
        ("gs-test", ["/home/kirocrew/.agents/setup", "--yolo"], b"y\ny\n"),
    ]


@pytest.mark.parametrize("backend", ["kiro", "claude", "codex"])
def test_run_setup_explicitly_targets_crew_backend(backend: str) -> None:
    """The selected backend is set up even if its executable is not detected."""
    import transport.academy as academy

    podman = _CapturePodman()
    loader = academy.AcademyLoader(podman, "gs-test", acp_backend=backend)
    loader._run_setup()

    setup_cmds = [cmd for _, cmd in podman.execs if cmd and cmd[0] == "/home/kirocrew/.agents/setup"]
    assert setup_cmds == [
        ["/home/kirocrew/.agents/setup", backend, "--yolo"],
        ["/home/kirocrew/.agents/setup", "--yolo"],
    ]


def test_run_setup_logs_warning_on_failure() -> None:
    """_run_setup failure logs a warning but does not raise."""
    import transport.academy as academy

    class _FailingPodman(_CapturePodman):
        def container_exec_stdin(self, name, cmd, stdin_data):
            if cmd and cmd[0] == "/home/kirocrew/.agents/setup":
                raise RuntimeError("setup script failed")
            return super().container_exec_stdin(name, cmd, stdin_data)

    podman = _FailingPodman()
    loader = academy.AcademyLoader(podman, "gs-test", acp_backend="kiro")
    # Should not raise
    loader._run_setup()


# ── copy_all routing tests ────────────────────────────────────────────────────

def test_copy_all_kiro_calls_copy_agents(tmp_path: Path) -> None:
    """copy_all for kiro backend calls _copy_agents (persona JSON delivery)."""
    import transport.academy as academy

    podman = _CapturePodman()
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "ghost.json").write_text('{"name":"ghost","description":"","tools":[]}')

    with (
        patch.object(academy, "_SKILLS_DIR", tmp_path / "skills"),
        patch.object(academy, "_AGENTS_DIR", agents_dir),
        patch.object(academy, "_load_crew_manifest", return_value={
            "agents": "*", "skills": "*", "steering": "*",
        }),
        patch("transport.academy.Path") as MockPath,
    ):
        # Patch so steering and skills sources appear empty
        class _NullPath:
            def __init__(self, *args):
                self._inner = Path(*args) if args else Path(".")

            def exists(self):
                return False

            def __getattr__(self, item):
                return getattr(self._inner, item)

        loader = academy.AcademyLoader(podman, "gs-test", acp_backend="kiro")

        called = {}

        def _fake_stage_skills(self):
            called["skills"] = True
            return []

        def _fake_stage_steering(self):
            called["steering"] = True
            return []

        def _fake_stage_mcp(self):
            called["mcp"] = True

        def _fake_run_setup(self):
            called["setup"] = True

        def _fake_copy_agents(self):
            called["agents"] = True
            return ["ghost.json"]

        loader._stage_skills = lambda: called.update(skills=True) or []
        loader._stage_steering = lambda: called.update(steering=True) or []
        loader._stage_mcp = lambda: called.update(mcp=True)
        loader._run_setup = lambda: called.update(setup=True)
        loader._copy_agents = lambda: called.update(agents=True) or ["ghost.json"]

        result = loader.copy_all()

    assert called.get("skills"), "_stage_skills was not called"
    assert called.get("steering"), "_stage_steering was not called"
    assert called.get("mcp"), "_stage_mcp was not called"
    assert called.get("setup"), "_run_setup was not called"
    assert called.get("agents"), "_copy_agents was not called for kiro backend"
    assert result["agents"] == ["ghost.json"]


@pytest.mark.parametrize("backend", ["claude", "codex"])
def test_copy_all_delivers_personas_for_every_backend(backend: str) -> None:
    """copy_all calls _copy_agents on non-kiro backends too.

    ~/.kiro/agents/ is KiroCrew's persona registry. Without it a claude or
    codex crew refuses every named dispatch ("Agent 'ghost' not found").
    """
    import transport.academy as academy

    podman = _CapturePodman()
    loader = academy.AcademyLoader(podman, "gs-test", acp_backend=backend)

    called = {}
    loader._stage_skills = lambda: []
    loader._stage_steering = lambda: []
    loader._stage_mcp = lambda: None
    loader._run_setup = lambda: None
    loader._copy_agents = lambda: called.update(agents=True) or ["ghost.json"]

    result = loader.copy_all()

    assert called.get("agents"), f"_copy_agents must be called for {backend} backend"
    assert result["agents"] == ["ghost.json"]


def test_copy_all_returns_expected_keys() -> None:
    """copy_all always returns a dict with agents, skills, steering keys."""
    import transport.academy as academy

    podman = _CapturePodman()
    loader = academy.AcademyLoader(podman, "gs-test", acp_backend="codex")

    loader._stage_skills = lambda: ["skill-a"]
    loader._stage_steering = lambda: ["steering.md"]
    loader._stage_mcp = lambda: None
    loader._run_setup = lambda: None
    loader._copy_agents = lambda: ["ghost.json"]

    result = loader.copy_all()
    assert set(result.keys()) == {"agents", "skills", "steering"}
    assert result["skills"] == ["skill-a"]
    assert result["steering"] == ["steering.md"]
    assert result["agents"] == ["ghost.json"]


def test_acp_backend_defaults_to_kiro() -> None:
    """AcademyLoader defaults to kiro backend when not specified."""
    import transport.academy as academy

    podman = _CapturePodman()
    loader = academy.AcademyLoader(podman, "gs-test")
    assert loader._acp_backend == "kiro"


# ---------------------------------------------------------------------------
# TRN-284 task 5.3: _load_comp_registry with missing file and malformed JSON
# ---------------------------------------------------------------------------

def test_load_comp_registry_missing_file_returns_default() -> None:
    """_load_comp_registry returns the default fallback when the file is missing."""
    import transport.academy as academy
    from pathlib import Path
    from unittest.mock import patch

    # Patch the path to point at a non-existent file
    missing_path = Path("/nonexistent/path/registry.json")
    with patch.object(academy, "_CREW_REGISTRY_PATH", missing_path):
        result = academy._load_comp_registry()

    # Must return a non-empty dict (the fallback)
    assert isinstance(result, dict), "Expected dict, got: " + repr(result)
    assert len(result) > 0, "Expected non-empty fallback dict"
    assert list(result) == ["spec-ops"]
    assert result["spec-ops"]["dir"] == "spec-ops"


def test_load_crew_manifest_without_entry_defaults_to_spec_ops(tmp_path) -> None:
    import json
    import transport.academy as academy
    from unittest.mock import patch

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"agents": ["agent-a"]}))
    with (
        patch.object(academy, "_resolve_comp", return_value={"dir": "spec-ops"}) as resolve,
        patch.object(academy, "_resolve_manifest_path", return_value=manifest),
    ):
        result = academy._load_crew_manifest()

    resolve.assert_called_once_with("spec-ops")
    assert result["agents"] == ["agent-a"]


def test_load_comp_registry_malformed_json_returns_default(tmp_path) -> None:
    """_load_comp_registry logs malformed JSON and returns its fallback."""
    import transport.academy as academy
    from pathlib import Path
    from unittest.mock import patch

    bad_json_file = tmp_path / "registry.json"
    bad_json_file.write_text("{this is not valid json")

    with patch.object(academy, "_CREW_REGISTRY_PATH", bad_json_file):
        result = academy._load_comp_registry()

    # Must return the default fallback (not raise, not return empty)
    assert isinstance(result, dict), "Expected dict on parse error, got: " + repr(result)
    assert len(result) > 0, "Expected non-empty fallback dict on parse error"


def test_load_comp_registry_accepts_legacy_compositions_key(tmp_path) -> None:
    """_load_comp_registry accepts the legacy 'compositions' key."""
    import json
    import transport.academy as academy
    from pathlib import Path
    from unittest.mock import patch, MagicMock

    registry_data = {
        "compositions": [
            {
                "name": "test-crew",
                "dir": "test-crew",
                "description": "A test comp",
            }
        ]
    }
    valid_json_file = tmp_path / "registry.json"
    valid_json_file.write_text(json.dumps(registry_data))

    # The function also checks that the directory exists under /crews/
    # Patch Path.is_dir to return True for the crew dir check
    original_is_dir = Path.is_dir

    def mock_is_dir(self):
        if "test-crew" in str(self):
            return True
        return original_is_dir(self)

    with (
        patch.object(academy, "_CREW_REGISTRY_PATH", valid_json_file),
        patch.object(Path, "is_dir", mock_is_dir),
    ):
        result = academy._load_comp_registry()

    assert isinstance(result, dict)
    assert "test-crew" in result


def _load_registry_data_for_comp_alias_test(tmp_path, registry_data):
    import json
    import transport.academy as academy
    from pathlib import Path
    from unittest.mock import patch

    registry_file = tmp_path / "registry.json"
    registry_file.write_text(json.dumps(registry_data))
    original_is_dir = Path.is_dir

    def mock_is_dir(path):
        if "test-crew" in str(path):
            return True
        return original_is_dir(path)

    with (
        patch.object(academy, "_CREW_REGISTRY_PATH", registry_file),
        patch.object(Path, "is_dir", mock_is_dir),
    ):
        return academy._load_comp_registry()


def test_load_comp_registry_reads_canonical_comps_key(tmp_path) -> None:
    entries = [{"name": "test-crew", "dir": "test-crew", "description": "A test comp"}]

    result = _load_registry_data_for_comp_alias_test(tmp_path, {"comps": entries})

    assert list(result) == ["test-crew"]


def test_load_comp_registry_accepts_equal_keys(tmp_path) -> None:
    entries = [{"name": "test-crew", "dir": "test-crew", "description": "A test comp"}]

    result = _load_registry_data_for_comp_alias_test(
        tmp_path,
        {"comps": entries, "compositions": entries},
    )

    assert list(result) == ["test-crew"]


def test_load_comp_registry_prefers_comps_on_conflict(tmp_path) -> None:
    result = _load_registry_data_for_comp_alias_test(
        tmp_path,
        {
            "comps": [{"name": "test-crew", "dir": "test-crew"}],
            "compositions": [{"name": "other-crew", "dir": "other-crew"}],
        },
    )

    assert list(result) == ["test-crew"]


def test_load_comp_registry_uses_legacy_when_comps_not_a_list(tmp_path) -> None:
    result = _load_registry_data_for_comp_alias_test(
        tmp_path,
        {
            "comps": None,
            "compositions": [{"name": "test-crew", "dir": "test-crew"}],
        },
    )

    assert list(result) == ["test-crew"]
