"""Academy composition registry, crew-manifest helpers, and validation.

Answers a single question for the transport package: "what academy
compositions exist, what do their manifests contain, and how do we validate
what the academy directory holds?" This is a different concern from crew
lifecycle management (launch, recovery, auth injection, monitoring), which
lives in ``lifecycle.py``.

Extracted from ``lifecycle.py`` by TRN-86.

Depends only on: stdlib and ``config.Config`` (the bottom of the transport
dependency graph) plus ``captain._resolve_orders_dir`` for the order-template
validation pass. It does NOT import from ``lifecycle``, ``server``,
``registry``, ``podman``, or ``files`` — there is no circular-import risk.
"""

from __future__ import annotations

import json
import logging
import re
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

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
cfg = Config.from_env()

# ── Config-driven constants ───────────────────────────────────────────────────
KC_IMAGE = cfg.kc_image

# Crew registry file (compositions)
_CREW_REGISTRY_PATH = Path("/crews/registry.json")

# Academy agents pool (bind-mounted from the host at /agents).
_AGENTS_DIR = Path("/agents")


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
