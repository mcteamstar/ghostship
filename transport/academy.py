"""Academy comp registry, crew-manifest helpers, and validation.

Answers a single question for the transport package: "what academy
comps exist, what do their manifests contain, and how do we validate
what the academy directory holds?" This is a different concern from crew
lifecycle management (launch, recovery, auth injection, monitoring), which
lives in ``lifecycle.py``.

Extracted from ``lifecycle.py``.

Depends only on: stdlib, ``config.Config``, ``constants``, and ``podman``
(for ``PodmanClient`` in ``AcademyLoader``). It does NOT import from
``lifecycle``, ``server``, ``registry``, or ``files`` — there is no
circular-import risk.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import stat
import tarfile
from pathlib import Path
from typing import Any

try:
    from config import Config  # container: flat /app/
except ImportError:
    from transport.config import Config  # local dev

try:
    from captain import _resolve_orders_dir  # container: flat /app/
except ModuleNotFoundError:
    from transport.captain import _resolve_orders_dir  # local dev

try:
    from podman import PodmanClient  # container: flat /app/  # noqa: F401
except ModuleNotFoundError:
    from transport.podman import PodmanClient  # local dev  # noqa: F401

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
cfg = Config.from_env()

# ── Config-driven constants ───────────────────────────────────────────────────
KC_IMAGE = cfg.kc_image

# Crew registry file (comps)
_CREW_REGISTRY_PATH = Path("/crews/registry.json")

# Academy agents pool (bind-mounted from the host at /agents).
_AGENTS_DIR = Path("/agents")
_SKILLS_DIR = Path("/skills")

# ── Container-side paths (must match Containerfile/crew image layout) ─────────
# _KIRO_AGENTS_DIR is still used for kiro-backend persona JSON delivery.
_KIRO_AGENTS_DIR = "/home/kirocrew/.kiro/agents"
_MCP_CATALOGUE_DIR = Path("/mcp")


# ── Comp registry ────────────────────────────────────────────────────────────

def _load_comp_registry() -> dict[str, dict]:
    """Read crews/registry.json and return a name → entry mapping.

    Validates each entry: name must be lowercase alphanum/hyphens and the
    corresponding dir must exist under /crews/. Invalid entries are logged
    and excluded. Falls back to a single "spec-ops" entry if the file is
    missing or unparseable.
    """
    fallback: dict[str, dict] = {
        "spec-ops": {
            "name": "spec-ops",
            "dir": "spec-ops",
            "description": "Default KiroCrew comp",
            "image": KC_IMAGE,
        }
    }
    if not _CREW_REGISTRY_PATH.exists():
        logger.info("No crew registry at %s — using default spec-ops comp", _CREW_REGISTRY_PATH)
        return fallback
    try:
        data = json.loads(_CREW_REGISTRY_PATH.read_text())
    except Exception as e:
        logger.warning("Failed to parse crew registry %s: %s — using fallback", _CREW_REGISTRY_PATH, e)
        return fallback

    # Canonical 'comps' wins over legacy 'compositions'. The legacy key is
    # only read when 'comps' is absent or not a list.
    comps_list = data.get("comps") if isinstance(data, dict) else None
    legacy_list = data.get("compositions") if isinstance(data, dict) else None
    if isinstance(comps_list, list):
        if legacy_list is not None and legacy_list != comps_list:
            logger.warning(
                "Crew registry %s defines conflicting 'comps' and legacy "
                "'compositions' keys — using 'comps'",
                _CREW_REGISTRY_PATH,
            )
    elif isinstance(legacy_list, list):
        if comps_list is not None:
            logger.warning(
                "Crew registry 'comps' is not a list — using legacy 'compositions'"
            )
        comps_list = legacy_list
    else:
        logger.warning(
            "Crew registry has no 'comps' or legacy 'compositions' list — using fallback"
        )
        return fallback

    registry: dict[str, dict] = {}
    name_pattern = re.compile(r'^[a-z0-9](?:[a-z0-9-]{0,48}[a-z0-9])?$')
    for entry in comps_list:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "")
        dir_name = entry.get("dir", "")
        if not name or not name_pattern.match(name):
            logger.warning("Comp registry: skipping entry with invalid name %r", name)
            continue
        if not dir_name or not Path(f"/crews/{dir_name}").is_dir():
            logger.warning("Comp registry: skipping %r — dir /crews/%s not found", name, dir_name)
            continue
        registry[name] = {
            "name": name,
            "dir": dir_name,
            "description": entry.get("description", ""),
            **({} if "image" not in entry else {"image": entry["image"]}),
        }

    if not registry:
        logger.warning("Comp registry is empty after validation — using fallback")
        return fallback

    return registry


def _resolve_comp(comp: str) -> dict | None:
    """Look up a comp name in the registry. Returns the entry or None."""
    return COMP_REGISTRY.get(comp)


def _resolve_manifest_path(entry: dict) -> Path:
    """Return the manifest.json path for a comp entry."""
    return Path(f"/crews/{entry['dir']}/manifest.json")


def _resolve_image(entry: dict) -> str:
    """Return the container image for a comp entry.

    Resolution order: entry-level image > KC_IMAGE env var.
    """
    return entry.get("image") or KC_IMAGE


COMP_REGISTRY: dict[str, dict] = _load_comp_registry()


# ── Crew manifest helpers ─────────────────────────────────────────────────────

def _load_crew_manifest(comp_entry: dict | None = None) -> dict[str, Any]:
    """Read the comp's manifest (see crew-manifest spec),
    deciding which agents, skills, and steering docs get copied into a
    crew. A missing manifest file, a missing key, or invalid JSON all
    degrade to "*" for the affected section(s) rather than failing
    crew setup."""
    default: dict[str, Any] = {"agents": "*", "skills": "*", "steering": "*"}
    if comp_entry is None:
        comp_entry = _resolve_comp("spec-ops") or {"dir": "spec-ops"}
    manifest_path = _resolve_manifest_path(comp_entry)
    if not manifest_path.exists():
        logger.warning(
            "No manifest at %s — defaulting to \"all\" for agents/skills/steering",
            manifest_path,
        )
        return default
    try:
        data = json.loads(manifest_path.read_text())
    except Exception as e:
        logger.warning(
            "Failed to parse manifest %s: %s — defaulting to \"all\"",
            manifest_path, e,
        )
        return default
    result = {key: data.get(key, "*") for key in default}
    # Include mcpServers if declared; absent key → None (skip mcp.json creation)
    if "mcpServers" in data:
        result["mcpServers"] = data["mcpServers"]
    return result


def _manifest_selects(selection: Any, name: str) -> bool:
    """True if `name` should be copied per a manifest section's selection
    ("*", or an explicit list of exact names)."""
    return selection == "*" or name in selection


def _agent_mcp_servers_for_tools(
    tools: Any, mcp_servers: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Return composition MCP entries named by an agent's tool grants."""
    if not isinstance(tools, list):
        return {}
    if "*" in tools:
        return mcp_servers
    selected: dict[str, dict[str, Any]] = {}
    for server_name, entry in mcp_servers.items():
        ref = f"@{server_name}"
        if any(
            isinstance(tool, str) and (tool == ref or tool.startswith(f"{ref}/"))
            for tool in tools
        ):
            selected[server_name] = entry
    return selected


def _substitute_env_vars(value: Any, env: dict[str, str]) -> Any:
    """Recursively substitute ${VAR} references in string values using env.

    Logs a warning for any unset variable but continues, writing the literal
    ${VAR} string as the value.
    """
    if isinstance(value, str):
        def _replace(match: "re.Match[str]") -> str:
            var_name = match.group(1)
            if var_name in env:
                return env[var_name]
            logger.warning(
                "mcp.json: environment variable ${%s} is not set — "
                "writing literal string",
                var_name,
            )
            return match.group(0)
        return re.sub(r"\$\{([^}]+)\}", _replace, value)
    if isinstance(value, dict):
        return {k: _substitute_env_vars(v, env) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env_vars(item, env) for item in value]
    return value


# ── Academy validation ────────────────────────────────────────────────────────

def _validate_academy() -> list[str]:
    """Validate the loaded Academy assets and return a list of warning strings.

    Runs once at transport startup (not per-launch). Never raises and never
    halts startup: operators may intentionally have a partial academy during
    development, so every problem is reported as a warning string for the
    caller to log at WARNING level. Three checks:

      1. Agent JSON schema — every ``*.json`` in the agents pool parses as JSON
         and carries ``name``, ``description`` and ``tools`` fields.
      2. Manifest cross-reference — every explicit name in a comp's
         ``agents``/``skills``/``steering`` arrays exists in the corresponding
         Academy pool. A section set to ``"*"`` is skipped.
      3. Order template front-matter — every ``*.md`` in the orders pool has
         parseable YAML front-matter and at least one ``{{...}}`` placeholder.

    Pool locations mirror the copy paths: ``_AGENTS_DIR`` (``/agents``),
    ``/skills``, ``/steering``, and ``_resolve_orders_dir()`` for orders.
    """
    try:
        import yaml as _yaml
        _yaml_safe_load = _yaml.safe_load
    except ImportError:
        # pyyaml not available (e.g. local dev without container deps) —
        # fall back to a minimal check: front-matter is non-empty text.
        def _yaml_safe_load(text: str) -> object:  # type: ignore[misc]
            if not text.strip():
                raise ValueError("empty front-matter")
            return text

    warnings: list[str] = []

    # ── 1. Agent JSON schema ──────────────────────────────────────────────────
    agents_dir = _AGENTS_DIR
    # The set of valid agent names for the manifest cross-reference below is
    # built from the *.json filenames (manifests list names as "<agent>.json").
    agent_pool: set[str] = set()
    if agents_dir.is_dir():
        for path in sorted(agents_dir.glob("*.json")):
            agent_pool.add(path.name)
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                warnings.append(
                    f"Academy agent {path.name}: not valid JSON ({e})"
                )
                continue
            if not isinstance(data, dict):
                warnings.append(
                    f"Academy agent {path.name}: top-level JSON is not an object"
                )
                continue
            for field in ("name", "description", "tools"):
                if field not in data:
                    warnings.append(
                        f"Academy agent {path.name}: missing required field {field!r}"
                    )

    # ── 2. Manifest cross-reference ───────────────────────────────────────────
    skills_pool: set[str] = set()
    skills_dir = Path("/skills")
    if skills_dir.is_dir():
        skills_pool = {p.name for p in skills_dir.iterdir() if p.is_dir()}

    steering_pool: set[str] = set()
    steering_dir = Path("/steering")
    if steering_dir.is_dir():
        steering_pool = {p.name for p in steering_dir.glob("*.md")}

    pools = {"agents": agent_pool, "skills": skills_pool, "steering": steering_pool}

    for comp_name, entry in COMP_REGISTRY.items():
        manifest = _load_crew_manifest(entry)
        for section, pool in pools.items():
            selection = manifest.get(section, "*")
            if selection == "*" or not isinstance(selection, list):
                continue
            for name in selection:
                if name not in pool:
                    warnings.append(
                        f"Crew comp {comp_name!r}: manifest {section} references "
                        f"unknown name {name!r} not present in the Academy "
                        f"{section} pool"
                    )

    # ── 3. Order template front-matter ────────────────────────────────────────
    orders_dir = _resolve_orders_dir()
    if orders_dir.is_dir():
        for path in sorted(p for p in orders_dir.glob("*.md") if not p.name.startswith(".")):
            try:
                content = path.read_text(encoding="utf-8")
            except Exception as e:
                warnings.append(f"Academy order {path.name}: could not read ({e})")
                continue
            front_matter = None
            if content.startswith("---\n"):
                end = content.find("\n---\n", 4)
                if end != -1:
                    front_matter = content[4:end]
            if front_matter is None:
                warnings.append(
                    f"Academy order {path.name}: missing YAML front-matter delimited by '---'"
                )
            else:
                try:
                    _yaml_safe_load(front_matter)
                except Exception as e:
                    warnings.append(
                        f"Academy order {path.name}: front-matter is not parseable YAML ({e})"
                    )
            if not re.search(r"\{\{[^}]+\}\}", content):
                warnings.append(
                    f"Academy order {path.name}: no {{{{...}}}} placeholder found"
                )

    return warnings


# ── Container-side .agents paths ─────────────────────────────────────────────
_AGENTS_HOME_DIR = "/home/kirocrew/.agents"
_AGENTS_SKILLS_DIR = f"{_AGENTS_HOME_DIR}/skills"
_AGENTS_CONTEXT_DIR = f"{_AGENTS_HOME_DIR}/context"
_AGENTS_MCP_DIR = f"{_AGENTS_HOME_DIR}/mcp"
_AGENTS_SETUP = f"{_AGENTS_HOME_DIR}/setup"


# ── AcademyLoader ─────────────────────────────────────────────────────────────


class AcademyLoader:
    """Parameterised copier for Academy assets into a running crew container.

    ``AcademyLoader(podman, container, comp_entry=None, acp_backend="kiro")``
    stages Academy content into the in-container ``.agents/`` directories, then
    execs ``.agents/setup`` to wire it to the native paths of every harness it
    detects in the image (TRN-264).

    Agent persona JSON is always delivered to ``~/.kiro/agents/``, KiroCrew's
    persona registry, whatever the crew's ``acp_backend``.

    Usage::

        loader = AcademyLoader(podman, container, comp_entry, acp_backend)
        result = loader.copy_all()
        # result == {"agents": [...], "skills": [...], "steering": [...]}

    The ``agents`` list in the result contains agent JSON filenames copied to
    ``~/.kiro/agents/``; it is used to populate
    ``enrolled_agents`` in the crew registry.
    """

    _KINDS = ("agents", "skills", "steering")

    def __init__(
        self,
        podman: "PodmanClient",
        container: str,
        comp_entry: dict | None = None,
        acp_backend: str = "kiro",
    ) -> None:
        self._podman = podman
        self._container = container
        self._comp_entry = comp_entry
        self._acp_backend = acp_backend or "kiro"
        self._staged_mcp_servers: dict[str, dict[str, Any]] | None = None

    # ── Public interface ──────────────────────────────────────────────────────

    def copy(self, kind: str) -> list[str]:
        """Copy Academy assets of *kind* into the crew container.

        *kind* must be one of ``"agents"``, ``"skills"``, or ``"steering"``.
        Returns the list of copied asset names (filenames / directory names).
        Raises ``ValueError`` for unknown kinds.

        .. warning::
            ``copy("skills")`` and ``copy("steering")`` stage content into the
            ``.agents/`` directories but do **not** call ``_run_setup()``.  The
            staged content is therefore not wired to the backend's harness paths
            until ``.agents/setup`` runs.  Prefer ``copy_all()`` for
            normal crew setup; use this method only when you need a single-kind
            operation and will call ``_run_setup()`` yourself.  ``copy("agents")``
            is exempt — it writes directly to ``~/.kiro/agents/``.
        """
        if kind == "agents":
            return self._copy_agents()
        if kind == "skills":
            return self._copy_skills()
        if kind == "steering":
            return self._copy_steering()
        raise ValueError(
            f"Unknown AcademyLoader kind {kind!r}. "
            f"Valid kinds: {self._KINDS!r}"
        )

    def copy_all(self) -> dict[str, list[str]]:
        """Stage all Academy asset kinds and wire them via .agents/setup.

        Stages skills, steering, and MCP into the in-container .agents/
        staging directories, then execs ``.agents/setup`` to wire everything to
        the native paths of every harness it detects in the crew image.

        Agent persona JSON is always delivered to ``~/.kiro/agents/``, whatever
        the crew's backend: it is KiroCrew's persona registry, which the gateway
        reads for every backend to resolve named dispatch and build each
        session's persona prompt.

        Returns ``{"agents": [...], "skills": [...], "steering": [...]}``.
        The ``agents`` list contains agent JSON filenames used to populate
        ``enrolled_agents``.
        """
        staged_skills = self._stage_skills()
        staged_steering = self._stage_steering()
        self._stage_mcp()
        self._run_setup()
        # Persona JSON is KiroCrew's registry, required on every backend.
        copied_agents = self._copy_agents()
        return {
            "agents": copied_agents,
            "skills": staged_skills,
            "steering": staged_steering,
        }

    # ── .agents staging methods ───────────────────────────────────────────────

    def _stage_skills(self) -> list[str]:
        """Tar-inject manifest-selected skills into /home/kirocrew/.agents/skills/.

        Replaces the old ``_copy_skills()`` kiro-specific delivery.
        Each manifest-selected skill directory is staged here; ``.agents/setup``
        then symlinks or copies them to the backend-native path at launch.
        """
        skills_src = _SKILLS_DIR
        if not skills_src.exists():
            logger.warning(
                "No /skills dir in transport container — skipping skill staging"
            )
            return []
        selection = _load_crew_manifest(self._comp_entry)["skills"]
        staged: list[str] = []
        for skill_dir in sorted(skills_src.iterdir(), key=lambda path: path.name):
            if skill_dir.is_symlink() or not skill_dir.is_dir():
                continue
            if not _manifest_selects(selection, skill_dir.name):
                continue
            try:
                files: list[tuple[Path, str, bytes, int]] = []
                for source in sorted(skill_dir.rglob("*"), key=lambda path: path.as_posix()):
                    if source.is_symlink():
                        continue
                    # Python bytecode left by local test runs never belongs in a crew.
                    if "__pycache__" in source.relative_to(skill_dir).parts or source.suffix == ".pyc":
                        continue
                    try:
                        source_stat = source.lstat()
                    except OSError:
                        continue
                    if not stat.S_ISREG(source_stat.st_mode):
                        continue
                    relative = source.relative_to(skill_dir).as_posix()
                    mode = 0o755 if source_stat.st_mode & 0o111 else 0o644
                    files.append((source, relative, source.read_bytes(), mode))
                if not files:
                    continue

                dest_dir = f"{_AGENTS_SKILLS_DIR}/{skill_dir.name}"
                self._podman.container_exec(
                    self._container, ["mkdir", "-p", dest_dir]
                )
                buf = io.BytesIO()
                with tarfile.open(fileobj=buf, mode="w") as tar:
                    for _source, relative, data, mode in files:
                        info = tarfile.TarInfo(name=relative)
                        info.size = len(data)
                        info.mode = mode
                        tar.addfile(info, io.BytesIO(data))
                buf.seek(0)
                self._podman.container_archive_put(
                    self._container, dest_dir, buf.read()
                )
                staged.append(skill_dir.name)
            except Exception as e:
                logger.warning("Failed to stage skill %s: %s", skill_dir.name, e)
        logger.info("Staged skills for %s: %s", self._container, staged)
        return staged

    def _stage_steering(self) -> list[str]:
        """Tar-inject manifest-selected steering docs into /home/kirocrew/.agents/context/.

        Replaces the old ``_copy_steering()`` kiro-specific delivery.
        """
        steering_src = Path("/steering")
        if not steering_src.exists():
            logger.warning(
                "No /steering dir in transport container — skipping steering staging"
            )
            return []
        selection = _load_crew_manifest(self._comp_entry)["steering"]
        staged: list[str] = []
        # Ensure destination directory exists in the container
        self._podman.container_exec(
            self._container, ["mkdir", "-p", _AGENTS_CONTEXT_DIR]
        )
        for doc in steering_src.glob("*.md"):
            if not _manifest_selects(selection, doc.name):
                continue
            try:
                data = doc.read_bytes()
                buf = io.BytesIO()
                with tarfile.open(fileobj=buf, mode="w") as tar:
                    ti = tarfile.TarInfo(name=doc.name)
                    ti.size = len(data)
                    ti.mode = 0o644
                    tar.addfile(ti, io.BytesIO(data))
                buf.seek(0)
                self._podman.container_archive_put(
                    self._container, _AGENTS_CONTEXT_DIR, buf.read()
                )
                staged.append(doc.name)
            except Exception as e:
                logger.warning("Failed to stage steering doc %s: %s", doc.name, e)
        logger.info("Staged steering docs for %s: %s", self._container, staged)
        return staged

    def _resolve_mcp_servers(self) -> dict[str, dict[str, Any]]:
        """Resolve the composition's MCP catalogue entries by server name."""
        manifest = _load_crew_manifest(self._comp_entry)
        mcp_servers_list = manifest.get("mcpServers")
        if not mcp_servers_list:
            return {}

        env = dict(os.environ)
        servers: dict[str, dict[str, Any]] = {}

        for server_name in mcp_servers_list:
            catalogue_path = _MCP_CATALOGUE_DIR / f"{server_name}.json"
            if not catalogue_path.is_file():
                logger.warning(
                    "mcp/servers.json: server %r not found in catalogue at %s — skipping",
                    server_name, catalogue_path,
                )
                continue
            try:
                entry = json.loads(catalogue_path.read_text())
            except Exception as e:
                logger.warning(
                    "mcp/servers.json: failed to parse catalogue entry %s: %s — skipping",
                    catalogue_path, e,
                )
                continue
            if not isinstance(entry, dict):
                logger.warning(
                    "mcp/servers.json: catalogue entry %s is not an object — skipping",
                    catalogue_path,
                )
                continue
            entry = _substitute_env_vars(entry, env)
            if "headers" in entry:
                entry["poolable"] = False
            # Academy-selected servers are active in harnesses using this flag.
            entry["disabled"] = False
            servers[server_name] = entry
        return servers

    def _stage_mcp(self) -> None:
        """Write resolved MCP entries into /home/kirocrew/.agents/mcp/.

        Replaces the old mcp.json delivery in ``_copy_agents()``.
        After env-var substitution, each resolved entry gets ``"disabled": false``
        so academy-delivered servers are active in harnesses using that field.
        ``.agents/setup`` merges the shared catalogue into native harness configs;
        the selected agent also receives the composition server directly in its
        ``mcpServers`` spec so KiroCrew can project it into ACP sessions.
        """
        servers_by_name = self._resolve_mcp_servers()
        self._staged_mcp_servers = servers_by_name
        if not servers_by_name:
            logger.info("mcp/servers.json: no valid server entries resolved — skipping write")
            return
        files = {
            "servers.json": json.dumps(servers_by_name, indent=2).encode(),
        }
        if self._acp_backend == "codex":
            # Codex's native config uses `enabled` rather than `disabled`. The
            # persona-level entry is what KiroCrew projects into a session, but
            # enable the same server in Codex's config for harness parity.
            files["codex.servers.json"] = json.dumps(
                {name: {"enabled": True} for name in servers_by_name}, indent=2
            ).encode()
        try:
            self._podman.container_exec(
                self._container, ["mkdir", "-p", _AGENTS_MCP_DIR]
            )
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w") as tar:
                for name, data in files.items():
                    ti = tarfile.TarInfo(name=name)
                    ti.size = len(data)
                    ti.mode = 0o644
                    tar.addfile(ti, io.BytesIO(data))
            buf.seek(0)
            self._podman.container_archive_put(
                self._container, _AGENTS_MCP_DIR, buf.read()
            )
            logger.info(
                "Wrote .agents/mcp/%s to %s (%d server(s))",
                ", ".join(files), self._container, len(servers_by_name),
            )
        except Exception as e:
            logger.warning(
                "Failed to write .agents/mcp/servers.json to %s: %s", self._container, e
            )

    def _run_setup(self) -> None:
        """Exec .agents/setup --yolo inside the crew container.

        Explicitly configure the selected ACP backend first because it may not
        have a standalone executable on PATH. Then configure every other
        detected harness as before. YOLO applies the shared unattended harness
        settings; KiroCrew runtime sandbox controls remain separate. Both setup
        confirmation prompts are answered through stdin for unattended crew
        provisioning.
        Non-zero exit is logged as
        a warning; crew launch continues so agents receive no academy wiring
        rather than failing to launch (per spec: graceful degradation).
        """
        commands = [
            [_AGENTS_SETUP, self._acp_backend, "--yolo"],
            [_AGENTS_SETUP, "--yolo"],
        ]
        for cmd in commands:
            try:
                self._podman.container_exec_stdin(
                    self._container,
                    cmd,
                    b"y\ny\n",
                )
                logger.info("Ran %s in %s", " ".join(cmd), self._container)
            except Exception as e:
                logger.warning(
                    "AcademyLoader: %s failed in %s: %s — "
                    "crew will launch without academy wiring",
                    " ".join(cmd), self._container, e,
                )

    # ── Agent persona JSON delivery (every backend) ───────────────────────────

    def _copy_agents(self) -> list[str]:
        """Copy selected personas and their composition MCP entries to ~/.kiro/agents/.

        Required for every backend: ``~/.kiro/agents/`` is KiroCrew's persona
        registry, not a kiro-cli-only location. Without it a claude or codex
        crew's gateway knows only its built-in agents and refuses named
        dispatch (``Agent 'ghost' not found``).
        """
        agents_src = Path("/agents")
        if not agents_src.exists():
            logger.warning(
                "No /agents dir in transport container — skipping agent copy"
            )
            return []
        manifest = _load_crew_manifest(self._comp_entry)
        selection = manifest["agents"]
        mcp_servers = (
            self._staged_mcp_servers
            if self._staged_mcp_servers is not None
            else self._resolve_mcp_servers()
        )
        copied: list[str] = []
        for af in agents_src.glob("*.json"):
            if not _manifest_selects(selection, af.name):
                continue
            try:
                data = af.read_bytes()
                if mcp_servers:
                    agent = json.loads(data)
                    tools = agent.get("tools") if isinstance(agent, dict) else None
                    selected_mcp_servers = _agent_mcp_servers_for_tools(
                        tools, mcp_servers
                    )
                    if selected_mcp_servers:
                        agent_mcp_servers = agent.get("mcpServers")
                        if not isinstance(agent_mcp_servers, dict):
                            agent_mcp_servers = {}
                        # An explicit persona entry takes precedence over the
                        # composition catalogue, matching Kiro's agent-level MCP
                        # config precedence over shared server settings.
                        agent["mcpServers"] = {
                            **selected_mcp_servers,
                            **agent_mcp_servers,
                        }
                        data = json.dumps(agent, indent=2).encode()
                buf = io.BytesIO()
                with tarfile.open(fileobj=buf, mode="w") as tar:
                    ti = tarfile.TarInfo(name=af.name)
                    ti.size = len(data)
                    tar.addfile(ti, io.BytesIO(data))
                buf.seek(0)
                self._podman.container_archive_put(
                    self._container, _KIRO_AGENTS_DIR, buf.read()
                )
                copied.append(af.name)
            except Exception as e:
                logger.warning("Failed to copy agent %s: %s", af.name, e)
        logger.info("Copied agents to %s: %s", self._container, copied)
        return copied

    # ── Legacy per-kind compatibility methods ─────────────────────────────────
    # These are retained so that lifecycle.py's one-line wrappers
    # (_copy_skills, _copy_steering) continue to resolve during the transition.
    # They delegate to the new staging methods but keep the old signature.

    def _copy_skills(self) -> list[str]:
        """Legacy: delegate to _stage_skills() for backward-compat wrappers."""
        return self._stage_skills()

    def _copy_steering(self) -> list[str]:
        """Legacy: delegate to _stage_steering() for backward-compat wrappers."""
        return self._stage_steering()
