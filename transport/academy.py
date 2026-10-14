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

import base64
import io
import json
import logging
import os
import re
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
    from constants import SCRIPTS_DIR  # container: flat /app/
except ModuleNotFoundError:
    from transport.constants import SCRIPTS_DIR  # local dev

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

# ── Container-side paths (must match Containerfile/crew image layout) ─────────
# These mirror the constants in lifecycle.py. They are defined here so
# AcademyLoader can use them without a circular import from lifecycle.
_KIRO_AGENTS_DIR = "/home/kirocrew/.kiro/agents"
_KIRO_SKILLS_DIR = "/home/kirocrew/.kiro/crew/skills"
_KIRO_STEERING_DIR = "/home/kirocrew/.kiro/steering"
_KIRO_MCP_JSON = "/home/kirocrew/.kiro/mcp.json"
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


# ── AcademyLoader ─────────────────────────────────────────────────────────────


class AcademyLoader:
    """Parameterised copier for Academy assets into a running crew container.

    ``AcademyLoader(podman, container, composition_entry=None)`` holds the three
    copy operations (``agents``, ``skills``, ``steering``) that were previously
    module-level functions in ``lifecycle.py``.  After TRN-240 task 4.2, each
    of those functions becomes a one-line wrapper delegating here; until then,
    both exist side-by-side.

    Usage::

        loader = AcademyLoader(podman, container, composition_entry)
        result = loader.copy_all()
        # result == {"agents": [...], "skills": [...], "steering": [...]}
    """

    _KINDS = ("agents", "skills", "steering")

    def __init__(
        self,
        podman: "PodmanClient",
        container: str,
        composition_entry: dict | None = None,
    ) -> None:
        self._podman = podman
        self._container = container
        self._composition_entry = composition_entry

    # ── Public interface ──────────────────────────────────────────────────────

    def copy(self, kind: str) -> list[str]:
        """Copy Academy assets of *kind* into the crew container.

        *kind* must be one of ``"agents"``, ``"skills"``, or ``"steering"``.
        Returns the list of copied asset names (filenames / directory names).
        Raises ``ValueError`` for unknown kinds.
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
        """Copy all three Academy asset kinds and return their results.

        Returns ``{"agents": [...], "skills": [...], "steering": [...]}``.
        """
        return {kind: self.copy(kind) for kind in self._KINDS}

    # ── Per-kind implementations ──────────────────────────────────────────────

    def _copy_agents(self) -> list[str]:
        """Copy agent JSONs selected by the crew manifest, plus write mcp.json."""
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

        # ── Write mcp.json from manifest.mcpServers ───────────────────────────
        mcp_servers_list = manifest.get("mcpServers")
        if not mcp_servers_list:
            return copied

        env = dict(os.environ)
        resolved_entries: dict[str, Any] = {}

        for server_name in mcp_servers_list:
            catalogue_path = _MCP_CATALOGUE_DIR / f"{server_name}.json"
            if not catalogue_path.is_file():
                logger.warning(
                    "mcp.json: server %r not found in catalogue at %s — skipping",
                    server_name, catalogue_path,
                )
                continue
            try:
                entry = json.loads(catalogue_path.read_text())
            except Exception as e:
                logger.warning(
                    "mcp.json: failed to parse catalogue entry %s: %s — skipping",
                    catalogue_path, e,
                )
                continue
            entry = _substitute_env_vars(entry, env)
            if "headers" in entry:
                entry["poolable"] = False
            resolved_entries[server_name] = entry

        if not resolved_entries:
            logger.info("mcp.json: no valid server entries resolved — skipping write")
            return copied

        mcp_json_data = json.dumps({"mcpServers": resolved_entries}, indent=2).encode()
        try:
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w") as tar:
                ti = tarfile.TarInfo(name="mcp.json")
                ti.size = len(mcp_json_data)
                tar.addfile(ti, io.BytesIO(mcp_json_data))
            buf.seek(0)
            mcp_dest_dir = str(Path(_KIRO_MCP_JSON).parent)
            self._podman.container_archive_put(
                self._container, mcp_dest_dir, buf.read()
            )
            logger.info(
                "Wrote mcp.json to %s with servers: %s",
                self._container, list(resolved_entries.keys()),
            )
        except Exception as e:
            logger.warning(
                "Failed to write mcp.json to %s: %s", self._container, e
            )

        return copied

    def _copy_skills(self) -> list[str]:
        """Copy skill SKILL.md files selected by the crew manifest."""
        skills_src = Path("/skills")
        if not skills_src.exists():
            logger.warning(
                "No /skills dir in transport container — skipping skill copy"
            )
            return []
        selection = _load_crew_manifest(self._composition_entry)["skills"]
        copied: list[str] = []
        for skill_dir in skills_src.iterdir():
            if not _manifest_selects(selection, skill_dir.name):
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            try:
                data = skill_md.read_bytes()
                dest_dir = f"{_KIRO_SKILLS_DIR}/{skill_dir.name}"
                self._podman.container_exec(
                    self._container, ["mkdir", "-p", dest_dir]
                )
                buf = io.BytesIO()
                with tarfile.open(fileobj=buf, mode="w") as tar:
                    ti = tarfile.TarInfo(name="SKILL.md")
                    ti.size = len(data)
                    tar.addfile(ti, io.BytesIO(data))
                buf.seek(0)
                self._podman.container_archive_put(
                    self._container, dest_dir, buf.read()
                )
                copied.append(skill_dir.name)
            except Exception as e:
                logger.warning("Failed to copy skill %s: %s", skill_dir.name, e)
        logger.info("Copied skills to %s: %s", self._container, copied)
        return copied

    def _copy_steering(self) -> list[str]:
        """Copy steering .md files selected by the crew manifest."""
        steering_src = Path("/steering")
        if not steering_src.exists():
            logger.warning(
                "No /steering dir in transport container — skipping steering copy"
            )
            return []
        selection = _load_crew_manifest(self._composition_entry)["steering"]
        copied: list[str] = []
        for doc in steering_src.glob("*.md"):
            if not _manifest_selects(selection, doc.name):
                continue
            try:
                b64 = base64.b64encode(doc.read_bytes()).decode()
                self._podman.container_exec(self._container, [
                    "python3", f"{SCRIPTS_DIR}/copy_steering.py",
                    _KIRO_STEERING_DIR, doc.name, b64,
                ])
                copied.append(doc.name)
            except Exception as e:
                logger.warning("Failed to copy steering doc %s: %s", doc.name, e)
        logger.info("Copied steering docs to %s: %s", self._container, copied)
        return copied
