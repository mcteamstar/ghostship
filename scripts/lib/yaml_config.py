#!/usr/bin/env python3
"""Standalone YAML config loader + migrator for install.sh (TRN-253).

install.sh shells out to this module to resolve the operator's configuration
from a layered set of YAML files and emit flat ``KEY=value`` lines that the
shell ``eval``s into its environment. The transport itself never imports this
module — ``transport/config.py:Config.from_env()`` is unchanged, and install.sh
still bakes the resolved env vars into compose.yml.

Design (see openspec/changes/trn-253-yaml-config/design.md):

  * D1 — PyYAML for parsing. Config files are never written back, so comment
    preservation (ruamel) is not needed.
  * D2 — Deep merge in Python: built-in defaults -> repo -> XDG, OR
    built-in defaults -> ``--config`` (repo+XDG skipped).
  * D3 — YAML nested keys map to the existing flat env var names via a single
    mapping table (``_KEY_MAP``), so ``Config.from_env()`` stays untouched.
  * D4 — Migration is a mechanical conf-key -> YAML-path mapping. Only
    non-default values are written; unknown keys become ``# UNKNOWN:`` comments.
  * D5 — XDG path per OS (resolved by install.sh and passed in).

Subcommands (argv[1]):

  resolve  --repo <path> --xdg <path> [--config <path>]
      Emit flat ``KEY=value`` lines (shell-quoted values) for the merged config.
      With ``--config``, the repo and xdg layers are ignored entirely.

  migrate  --conf <path> --out <path>
      Read a legacy ``ghostship.conf`` (shell key=value), write a
      ``ghostship.yaml`` holding only non-default values, and print any unknown
      conf keys (one ``UNKNOWN: KEY`` line per unmapped key) to stdout.

This module is intentionally dependency-light: only PyYAML and the stdlib.
"""

from __future__ import annotations

import argparse
import os
import shlex
import sys
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - install.sh ensures PyYAML is present
    yaml = None  # type: ignore[assignment]


def _require_yaml() -> None:
    """Abort with a clear message when PyYAML is unavailable.

    Called from the CLI entry points rather than at import time so that
    importing this module (e.g. from the unit tests) never terminates the
    interpreter — a missing dependency surfaces as a normal error instead.
    """
    if yaml is None:
        sys.stderr.write(
            "error: PyYAML is required to parse the YAML config. "
            "Install it with `pip install pyyaml`.\n"
        )
        raise SystemExit(2)


# ── Built-in defaults ─────────────────────────────────────────────────────────
# Flat env-var-name -> default value. Mirrors the literal defaults block near
# the top of scripts/install.sh AND the Config dataclass field defaults in
# transport/config.py. Values are strings so they round-trip through the shell
# unchanged; booleans use the lowercase "true"/"false" form install.sh expects.
#
# Keep this in sync with install.sh's defaults block. The config sync CI test
# (tests/unit/test_config.py) asserts every Config dataclass field has a
# matching entry in config/ghostship.yaml.example; this table is the install
# side of the same contract.
DEFAULTS: dict[str, str] = {
    # ── network ──
    "HOST": "0.0.0.0",
    "PORT": "64057",
    "GA_HOST_URL": "",
    "GA_API_KEY": "",
    "GA_REQUIRE_API_KEY": "error",
    "GA_TLS_CERTFILE": "",
    "GA_TLS_KEYFILE": "",
    # ── crew lifecycle ──
    "GA_MAX_CREWS": "20",
    "GA_MAX_ACTIVE_CREWS": "3",
    "GA_IDLE_TIMEOUT_SECS": "300",
    "GA_SUBAGENT_TIMEOUT_SECS": "3600",
    "GA_SUBAGENT_MAX_TURNS": "200",
    "GA_BATCH_MAX_TASKS": "20",
    "GA_PICKUP_MAX_POLL_SECS": "30",
    # ── memory gate ──
    "GA_MIN_FREE_MEM_GB": "2.0",
    "GA_SPAWN_MIN_MEMORY_GB": "1.5",
    "GA_RESOURCE_PRESSURE_GB": "2.0",
    "GA_RESOURCE_CRITICAL_GB": "1.0",
    "GA_SPAWN_PRESSURE_ESCALATE_CYCLES": "3",
    # ── model ──
    "KC_MODEL_OVERRIDE": "",
    "KC_MODEL_DEFAULT": "",
    # ── git identity ──
    "GA_GIT_AUTHOR_NAME": "",
    "GA_GIT_AUTHOR_EMAIL": "",
    # ── backends ──
    "GA_CREW_AGENT": "kiro",
    "KIRO_IDENTITY_PROVIDER": "",
    "KIRO_REGION": "",
    "KIRO_LICENSE": "",
    "ANTHROPIC_BASE_URL": "",
    "OPENAI_BASE_URL": "",
    # ── user-defined orders ──
    "GA_ORDERS_DIR": "",
    # ── images (advanced) ──
    "PODMAN_SOCKET": "/run/user/1000/podman/podman.sock",
    "KC_IMAGE": "localhost/spec-ops:latest",
    "KC_BASE_IMAGE": "",
    # ── portal / caddy ──
    "GA_PORTAL_TLS_MODE": "off",
    "GA_PORTAL_DOMAIN": "",
    "GA_PORTAL_SESSION_TTL_SECS": "86400",
    # ── dashboard port allocation ──
    "GA_DASHBOARD_PORT_RANGE_START": "64058",
    "GA_DASHBOARD_PORT_RANGE_SIZE": "64",
    "GA_DASHBOARD_DEFAULT": "false",
    # ── rate limiting ──
    "GA_RATE_LIMIT_ENABLED": "true",
    "GA_RATE_LIMIT_LOGIN_GET": "30:60",
    "GA_RATE_LIMIT_LOGIN_POST": "5:300",
    "GA_RATE_LIMIT_MCP": "300:60",
    "GA_RATE_LIMIT_FILES": "60:60",
    "GA_RATE_LIMIT_CREW_API": "120:60",
    "GA_RATE_LIMIT_DASHBOARD_AUTH": "600:60",
    # ── dedicated podman machine ──
    "GA_DEDICATED_MACHINE": "true",
    "GA_MACHINE_NAME": "ghost-academy",
    "GA_MACHINE_CPUS": "8",
    "GA_MACHINE_MEMORY": "16384",
    "GA_MACHINE_DISK": "100",
}


# ── YAML path -> env var mapping ──────────────────────────────────────────────
# A YAML "path" is the tuple of nested keys (e.g. ("network", "port")). Every
# configurable env var has exactly one canonical YAML path. The mapping is
# bidirectional: flatten uses path->env, migration uses env->path.
#
# The nesting groups keys into the logical sections required by the spec:
# network, crew, model, backends, portal, machine (plus rate_limit and images).
_KEY_MAP: dict[tuple[str, ...], str] = {
    # network
    ("network", "host"): "HOST",
    ("network", "port"): "PORT",
    ("network", "host_url"): "GA_HOST_URL",
    ("network", "api_key"): "GA_API_KEY",
    ("network", "require_api_key"): "GA_REQUIRE_API_KEY",
    ("network", "tls_certfile"): "GA_TLS_CERTFILE",
    ("network", "tls_keyfile"): "GA_TLS_KEYFILE",
    # crew
    ("crew", "max_crews"): "GA_MAX_CREWS",
    ("crew", "max_active"): "GA_MAX_ACTIVE_CREWS",
    ("crew", "idle_timeout_secs"): "GA_IDLE_TIMEOUT_SECS",
    ("crew", "subagent_timeout_secs"): "GA_SUBAGENT_TIMEOUT_SECS",
    ("crew", "subagent_max_turns"): "GA_SUBAGENT_MAX_TURNS",
    ("crew", "batch_max_tasks"): "GA_BATCH_MAX_TASKS",
    ("crew", "pickup_max_poll_secs"): "GA_PICKUP_MAX_POLL_SECS",
    ("crew", "orders_dir"): "GA_ORDERS_DIR",
    ("crew", "git_author_name"): "GA_GIT_AUTHOR_NAME",
    ("crew", "git_author_email"): "GA_GIT_AUTHOR_EMAIL",
    # crew.memory
    ("crew", "memory", "min_free_mem_gb"): "GA_MIN_FREE_MEM_GB",
    ("crew", "memory", "spawn_min_memory_gb"): "GA_SPAWN_MIN_MEMORY_GB",
    ("crew", "memory", "resource_pressure_gb"): "GA_RESOURCE_PRESSURE_GB",
    ("crew", "memory", "resource_critical_gb"): "GA_RESOURCE_CRITICAL_GB",
    ("crew", "memory", "spawn_pressure_escalate_cycles"): "GA_SPAWN_PRESSURE_ESCALATE_CYCLES",
    # model
    ("model", "override"): "KC_MODEL_OVERRIDE",
    ("model", "default"): "KC_MODEL_DEFAULT",
    # backends
    ("backends", "agent"): "GA_CREW_AGENT",
    ("backends", "kiro", "identity_provider"): "KIRO_IDENTITY_PROVIDER",
    ("backends", "kiro", "region"): "KIRO_REGION",
    ("backends", "kiro", "license"): "KIRO_LICENSE",
    ("backends", "claude", "base_url"): "ANTHROPIC_BASE_URL",
    ("backends", "codex", "base_url"): "OPENAI_BASE_URL",
    # images (advanced)
    ("images", "podman_socket"): "PODMAN_SOCKET",
    ("images", "kc_image"): "KC_IMAGE",
    ("images", "kc_base_image"): "KC_BASE_IMAGE",
    # portal
    ("portal", "tls_mode"): "GA_PORTAL_TLS_MODE",
    ("portal", "domain"): "GA_PORTAL_DOMAIN",
    ("portal", "session_ttl_secs"): "GA_PORTAL_SESSION_TTL_SECS",
    ("portal", "dashboard_port_range_start"): "GA_DASHBOARD_PORT_RANGE_START",
    ("portal", "dashboard_port_range_size"): "GA_DASHBOARD_PORT_RANGE_SIZE",
    ("portal", "dashboard_default"): "GA_DASHBOARD_DEFAULT",
    # portal.rate_limit
    ("portal", "rate_limit", "enabled"): "GA_RATE_LIMIT_ENABLED",
    ("portal", "rate_limit", "login_get"): "GA_RATE_LIMIT_LOGIN_GET",
    ("portal", "rate_limit", "login_post"): "GA_RATE_LIMIT_LOGIN_POST",
    ("portal", "rate_limit", "mcp"): "GA_RATE_LIMIT_MCP",
    ("portal", "rate_limit", "files"): "GA_RATE_LIMIT_FILES",
    ("portal", "rate_limit", "crew_api"): "GA_RATE_LIMIT_CREW_API",
    ("portal", "rate_limit", "dashboard_auth"): "GA_RATE_LIMIT_DASHBOARD_AUTH",
    # machine (dedicated podman machine)
    ("machine", "dedicated"): "GA_DEDICATED_MACHINE",
    ("machine", "name"): "GA_MACHINE_NAME",
    ("machine", "cpus"): "GA_MACHINE_CPUS",
    ("machine", "memory"): "GA_MACHINE_MEMORY",
    ("machine", "disk"): "GA_MACHINE_DISK",
}

# env var -> YAML path, derived once (used by migration).
_ENV_TO_PATH: dict[str, tuple[str, ...]] = {env: path for path, env in _KEY_MAP.items()}

# Deprecated conf keys that map to a current env var (TRN-226 renames and the
# GA_PORTAL_PORT -> PORT migration guard). Applied during migration so an old
# conf's deprecated names land on the right YAML path.
_DEPRECATED_CONF_ALIASES: dict[str, str] = {
    "GA_PORTAL_PORT": "PORT",
    "GA_CREW_ACP_BACKEND": "GA_CREW_AGENT",
    "GA_CREW_ANTHROPIC_BASE_URL": "ANTHROPIC_BASE_URL",
    "GA_CREW_OPENAI_BASE_URL": "OPENAI_BASE_URL",
}

# Conf keys that are intentionally dropped on migration (never written to YAML):
# backend credentials are no longer installer-managed (TRN-233), and
# GA_AGENT_BACKENDS folded into GA_CREW_AGENT (TRN-213). They are not "unknown"
# — they are deliberately discarded — so they do not become UNKNOWN comments.
_DROPPED_CONF_KEYS: frozenset[str] = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "KIRO_API_KEY",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "GA_CREW_ANTHROPIC_API_KEY",
        "GA_CREW_OPENAI_API_KEY",
        "GA_TRANSPORT_SECRET",
        "GA_AGENT_BACKENDS",
    }
)


# ── Loading / merging ─────────────────────────────────────────────────────────


def load_yaml(path: str) -> dict[str, Any]:
    """Load a YAML file into a dict. Returns {} if the file is missing or empty.

    Raises ValueError with a clear message on a YAML syntax error, or when the
    top-level document is not a mapping.
    """
    if not path or not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: YAML parse error: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(
            f"{path}: top-level YAML must be a mapping (got {type(data).__name__})"
        )
    return data


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` on top of ``base``.

    Dict values are merged key-by-key; every other value type (scalars AND
    lists) is replaced entirely by the override. Returns a new dict — neither
    argument is mutated.
    """
    result: dict[str, Any] = dict(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _defaults_tree() -> dict[str, Any]:
    """Build the nested dict of built-in defaults from DEFAULTS + _KEY_MAP."""
    tree: dict[str, Any] = {}
    for path, env in _KEY_MAP.items():
        if env not in DEFAULTS:
            continue
        cursor = tree
        for segment in path[:-1]:
            cursor = cursor.setdefault(segment, {})
        cursor[path[-1]] = DEFAULTS[env]
    return tree


def resolve_config(
    repo_path: str,
    xdg_path: str,
    explicit_path: str | None,
) -> dict[str, Any]:
    """Resolve the merged config tree.

    With ``explicit_path`` (the ``--config`` flag): built-in defaults then the
    explicit file only — repo and XDG layers are skipped (D6).

    Without it: built-in defaults -> repo -> XDG (D2).
    """
    merged = _defaults_tree()
    if explicit_path:
        merged = deep_merge(merged, load_yaml(explicit_path))
    else:
        merged = deep_merge(merged, load_yaml(repo_path))
        merged = deep_merge(merged, load_yaml(xdg_path))
    return merged


# ── Flattening to env vars ────────────────────────────────────────────────────


def _normalise_scalar(value: Any) -> str:
    """Render a YAML scalar as the string install.sh expects.

    Booleans become lowercase "true"/"false"; None becomes an empty string;
    everything else is str()'d. Lists/dicts are not valid leaf values and are
    rejected by the caller.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def flatten_to_env(merged: dict[str, Any]) -> dict[str, str]:
    """Flatten a merged config tree into ``{ENV_VAR: value}``.

    Walks the tree against ``_KEY_MAP``. Any leaf whose path is not in the map
    is reported via ``unknown_keys`` on the returned object's companion — here
    we simply ignore unmapped paths for the env output (the caller warns about
    them separately via :func:`collect_unknown_paths`).
    """
    env: dict[str, str] = {}
    for path, var in _KEY_MAP.items():
        value = _lookup_path(merged, path)
        if value is _MISSING:
            continue
        env[var] = _normalise_scalar(value)
    return env


_MISSING = object()


def _lookup_path(tree: dict[str, Any], path: tuple[str, ...]) -> Any:
    """Return the leaf at ``path`` in ``tree``, or ``_MISSING`` if absent."""
    cursor: Any = tree
    for segment in path:
        if not isinstance(cursor, dict) or segment not in cursor:
            return _MISSING
        cursor = cursor[segment]
    return cursor


def collect_unknown_paths(
    tree: dict[str, Any], prefix: tuple[str, ...] = ()
) -> list[str]:
    """Return dotted key paths present in ``tree`` but not in ``_KEY_MAP``.

    A path is "known" if it is a mapped leaf OR a prefix of one (an intermediate
    section). Unknown leaves and unknown sections are both reported.
    """
    known_prefixes: set[tuple[str, ...]] = set()
    for path in _KEY_MAP:
        for i in range(1, len(path) + 1):
            known_prefixes.add(path[:i])

    unknown: list[str] = []

    def _walk(node: Any, path: tuple[str, ...]) -> None:
        if not isinstance(node, dict):
            return
        for key, value in node.items():
            here = path + (key,)
            if here in _KEY_MAP:
                continue  # mapped leaf
            if here in known_prefixes:
                _walk(value, here)  # known section — recurse
            else:
                unknown.append(".".join(here))

    _walk(tree, prefix)
    return unknown


# ── Migration ─────────────────────────────────────────────────────────────────


def _parse_conf(conf_path: str) -> list[tuple[str, str]]:
    """Parse a legacy shell-style ghostship.conf into ordered (key, value) pairs.

    Handles ``KEY=value``, ``KEY="value"``, ``export KEY=value`` and inline
    comments; skips blank lines and full-line comments. Preserves file order so
    the generated YAML is stable.
    """
    pairs: list[tuple[str, str]] = []
    with open(conf_path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            # Strip surrounding quotes (either kind). shlex handles escapes and
            # trailing inline comments on unquoted values.
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            else:
                # Drop an inline comment on an unquoted value.
                try:
                    parts = shlex.split(value, comments=True)
                    value = parts[0] if parts else ""
                except ValueError:
                    pass
            pairs.append((key, value))
    return pairs


def migrate_conf(conf_path: str, yaml_path: str) -> list[str]:
    """Convert a legacy ghostship.conf to ghostship.yaml.

    Writes ``yaml_path`` holding only the keys whose value differs from the
    built-in default, nested under their YAML paths with a trailing ``# UNKNOWN``
    comment section for any conf key that is neither mapped nor deliberately
    dropped. Returns the list of unknown conf keys (empty when all are handled).
    """
    pairs = _parse_conf(conf_path)
    tree: dict[str, Any] = {}
    unknown: list[tuple[str, str]] = []

    for key, value in pairs:
        env = _DEPRECATED_CONF_ALIASES.get(key, key)
        if env in _DROPPED_CONF_KEYS or key in _DROPPED_CONF_KEYS:
            continue
        path = _ENV_TO_PATH.get(env)
        if path is None:
            unknown.append((key, value))
            continue
        # Only write non-default values (override-file principle, D4).
        if DEFAULTS.get(env, _MISSING) == value:
            continue
        cursor = tree
        for segment in path[:-1]:
            cursor = cursor.setdefault(segment, {})
        cursor[path[-1]] = _coerce_yaml_scalar(value)

    lines: list[str] = [
        "# Migrated from ghostship.conf by install.sh (TRN-253).",
        "# Only values that differed from the built-in defaults are shown.",
        "# Full reference: config/ghostship.yaml.example and docs/configuration.md",
        "",
    ]
    if tree:
        lines.append(yaml.safe_dump(tree, default_flow_style=False, sort_keys=True).rstrip())
    else:
        lines.append("# (no non-default values were set)")
    if unknown:
        lines.append("")
        lines.append("# Unmapped keys from the old ghostship.conf — handle manually:")
        for key, value in unknown:
            lines.append(f"# UNKNOWN: {key}={value}")

    with open(yaml_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    return [key for key, _ in unknown]


def _coerce_yaml_scalar(value: str) -> Any:
    """Coerce a conf string value to a native YAML scalar where unambiguous.

    Integers and the booleans true/false become native types so the YAML reads
    naturally; everything else stays a string.
    """
    low = value.lower()
    if low in ("true", "false"):
        return low == "true"
    if value and (value.isdigit() or (value[0] == "-" and value[1:].isdigit())):
        return int(value)
    return value


# ── CLI ───────────────────────────────────────────────────────────────────────


def _cmd_resolve(args: argparse.Namespace) -> int:
    merged = resolve_config(
        repo_path=args.repo or "",
        xdg_path=args.xdg or "",
        explicit_path=args.config or None,
    )
    for path in collect_unknown_paths(merged):
        sys.stderr.write(f"warning: unknown config key '{path}' ignored\n")
    env = flatten_to_env(merged)
    for key in sorted(env):
        # Shell-quote the value so eval is safe for spaces/special chars.
        sys.stdout.write(f"{key}={shlex.quote(env[key])}\n")
    return 0


def _cmd_migrate(args: argparse.Namespace) -> int:
    if not os.path.isfile(args.conf):
        sys.stderr.write(f"error: conf file does not exist: {args.conf}\n")
        return 1
    unknown = migrate_conf(args.conf, args.out)
    for key in unknown:
        sys.stdout.write(f"UNKNOWN: {key}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    _require_yaml()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_resolve = sub.add_parser("resolve", help="emit flat KEY=value env lines")
    p_resolve.add_argument("--repo", default="", help="repo-level ghostship.yaml path")
    p_resolve.add_argument("--xdg", default="", help="XDG override ghostship.yaml path")
    p_resolve.add_argument("--config", default="", help="explicit --config path (skips repo+xdg)")
    p_resolve.set_defaults(func=_cmd_resolve)

    p_migrate = sub.add_parser("migrate", help="convert ghostship.conf to ghostship.yaml")
    p_migrate.add_argument("--conf", required=True, help="legacy ghostship.conf path")
    p_migrate.add_argument("--out", required=True, help="output ghostship.yaml path")
    p_migrate.set_defaults(func=_cmd_migrate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
