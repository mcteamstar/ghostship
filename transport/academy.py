"""Academy composition registry, crew-manifest helpers, and validation.

Answers a single question for the transport package: "what academy
compositions exist, what do their manifests contain, and how do we validate
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

# Crew registry file (compositions)
_CREW_REGISTRY_PATH = Path("/crews/registry.json")

# Academy agents pool (bind-mounted from the host at /agents).
_AGENTS_DIR = Path("/agents")
_SKILLS_DIR = Path("/skills")

# ── Container-side paths (must match Containerfile/crew image layout) ─────────
# _KIRO_AGENTS_DIR is still used for kiro-backend persona JSON delivery.
_KIRO_AGENTS_DIR = "/home/kirocrew/.kiro/agents"
_MCP_CATALOGUE_DIR = Path("/mcp")


# ── Composition registry ──────────────────────────────────────────────────────

def _load_composition_registry() -> dict[str, dict]:
    """Read crews/registry.json and return a name → entry mapping.

    Validates each entry: name must be lowercase alphanum/hyphens and the
    corresponding dir must exist under /crews/. Invalid entries are logged
    and excluded. Falls back to a single "kirocrew" entry if the file is
    missing or unparseable.
    """
    fallback: dict[str, dict] = {
        "spec-ops": {
            "name": "spec-ops",
            "dir": "spec-ops",
            "description": "Default KiroCrew crew type",
            "image": KC_IMAGE,
        }
    }
    if not _CREW_REGISTRY_PATH.exists():
        logger.info("No crew registry at %s — using default spec-ops type", _CREW_REGISTRY_PATH)
        return fallback
    try:
        data = json.loads(_CREW_REGISTRY_PATH.read_text())
    except Exception as e:
        logger.warning("Failed to parse crew registry %s: %s — using fallback", _CREW_REGISTRY_PATH, e)
        return fallback

    types_list = data.get("compositions")
    if not isinstance(types_list, list):
        logger.warning("Crew registry 'compositions' is not a list — using fallback")
        return fallback

    registry: dict[str, dict] = {}
    name_pattern = re.compile(r'^[a-z0-9](?:[a-z0-9-]{0,48}[a-z0-9])?$')
    for entry in types_list:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "")
        dir_name = entry.get("dir", "")
        if not name or not name_pattern.match(name):
            logger.warning("Crew type registry: skipping entry with invalid name %r", name)
            continue
        if not dir_name or not Path(f"/crews/{dir_name}").is_dir():
            logger.warning("Crew type registry: skipping %r — dir /crews/%s not found", name, dir_name)
            continue
        registry[name] = {
            "name": name,
            "dir": dir_name,
            "description": entry.get("description", ""),
            **({} if "image" not in entry else {"image": entry["image"]}),
        }

    if not registry:
        logger.warning("Crew type registry is empty after validation — using fallback")
        return fallback

    return registry


def _resolve_composition(composition: str) -> dict | None:
    """Look up a crew type name in the registry. Returns the entry or None."""
    return COMPOSITION_REGISTRY.get(composition)


def _resolve_manifest_path(entry: dict) -> Path:
    """Return the manifest.json path for a crew type entry."""
    return Path(f"/crews/{entry['dir']}/manifest.json")


def _resolve_image(entry: dict) -> str:
    """Return the container image for a crew type entry.

    Resolution order: entry-level image > KC_IMAGE env var.
    """
    return entry.get("image") or KC_IMAGE


COMPOSITION_REGISTRY: dict[str, dict] = _load_composition_registry()


# ── Crew manifest helpers ─────────────────────────────────────────────────────

def _load_crew_manifest(composition_entry: dict | None = None) -> dict[str, Any]:
    """Read the crew type's manifest (see crew-manifest spec),
    deciding which agents, skills, and steering docs get copied into a
    crew. A missing manifest file, a missing key, or invalid JSON all
    degrade to "*" for the affected section(s) rather than failing
    crew setup."""
    default: dict[str, Any] = {"agents": "*", "skills": "*", "steering": "*"}
    if composition_entry is None:
        composition_entry = _resolve_composition("kirocrew") or {"dir": "kirocrew"}
    manifest_path = _resolve_manifest_path(composition_entry)
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
      2. Manifest cross-reference — every explicit name in a crew type's
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

    for crew_type, entry in COMPOSITION_REGISTRY.items():
        manifest = _load_crew_manifest(entry)
        for section, pool in pools.items():
            selection = manifest.get(section, "*")
            if selection == "*" or not isinstance(selection, list):
                continue
            for name in selection:
                if name not in pool:
                    warnings.append(
                        f"Crew type {crew_type!r}: manifest {section} references "
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

    ``AcademyLoader(podman, container, composition_entry=None, acp_backend="kiro")``
    stages Academy content into the in-container ``.agents/`` directories, then
    execs ``.agents/setup`` to wire it to the native paths of every harness it
    detects in the image (TRN-264).

    Agent persona JSON is always delivered to ``~/.kiro/agents/``, KiroCrew's
    persona registry, whatever the crew's ``acp_backend``.

    Usage::

        loader = AcademyLoader(podman, container, composition_entry, acp_backend)
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
        composition_entry: dict | None = None,
        acp_backend: str = "kiro",
    ) -> None:
        self._podman = podman
        self._container = container
        self._composition_entry = composition_entry
        self._acp_backend = acp_backend or "kiro"

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
        selection = _load_crew_manifest(self._composition_entry)["skills"]
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
        selection = _load_crew_manifest(self._composition_entry)["steering"]
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

    def _stage_mcp(self) -> None:
        """Write resolved MCP catalogue entries into /home/kirocrew/.agents/mcp/servers.json.

        Replaces the old mcp.json delivery in ``_copy_agents()``.
        After env-var substitution, each resolved entry gets ``"disabled": false``
        so academy-delivered servers are active by default (D3 in design.md).
        ``.agents/setup`` reads this file and writes each detected harness's
        native MCP config (e.g. kiro mcp.json, claude .claude.json).
        """
        manifest = _load_crew_manifest(self._composition_entry)
        mcp_servers_list = manifest.get("mcpServers")
        if not mcp_servers_list:
            return

        env = dict(os.environ)
        resolved_entries: list[dict[str, Any]] = []

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
            entry = _substitute_env_vars(entry, env)
            if "headers" in entry:
                entry["poolable"] = False
            # D3: explicitly set disabled=false so academy-delivered servers are active
            entry["disabled"] = False
            resolved_entries.append({"name": server_name, **entry})

        if not resolved_entries:
            logger.info("mcp/servers.json: no valid server entries resolved — skipping write")
            return

        servers_json_data = json.dumps(resolved_entries, indent=2).encode()
        try:
            self._podman.container_exec(
                self._container, ["mkdir", "-p", _AGENTS_MCP_DIR]
            )
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w") as tar:
                ti = tarfile.TarInfo(name="servers.json")
                ti.size = len(servers_json_data)
                ti.mode = 0o644
                tar.addfile(ti, io.BytesIO(servers_json_data))
            buf.seek(0)
            self._podman.container_archive_put(
                self._container, _AGENTS_MCP_DIR, buf.read()
            )
            logger.info(
                "Wrote .agents/mcp/servers.json to %s (%d server(s))",
                self._container, len(resolved_entries),
            )
        except Exception as e:
            logger.warning(
                "Failed to write .agents/mcp/servers.json to %s: %s", self._container, e
            )

    def _run_setup(self) -> None:
        """Exec .agents/setup inside the crew container.

        A single call after all staging is complete wires skills, steering, and
        MCP to the native paths of every harness ``.agents/setup`` detects in
        the image, not only the crew's own backend. Harness detection is left
        to ``.agents/setup``.  Non-zero exit is logged as
        a warning; crew launch continues so agents receive no academy wiring
        rather than failing to launch (per spec: graceful degradation).
        """
        try:
            self._podman.container_exec(
                self._container,
                [_AGENTS_SETUP],
            )
            logger.info("Ran .agents/setup in %s", self._container)
        except Exception as e:
            logger.warning(
                "AcademyLoader: .agents/setup failed in %s: %s — "
                "crew will launch without academy wiring",
                self._container, e,
            )

    # ── Agent persona JSON delivery (every backend) ───────────────────────────

    def _copy_agents(self) -> list[str]:
        """Copy agent JSONs selected by the crew manifest to ~/.kiro/agents/.

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
        manifest = _load_crew_manifest(self._composition_entry)
        selection = manifest["agents"]
        copied: list[str] = []
        for af in agents_src.glob("*.json"):
            if not _manifest_selects(selection, af.name):
                continue
            try:
                data = af.read_bytes()
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
