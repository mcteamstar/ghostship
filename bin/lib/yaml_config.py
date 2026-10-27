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

  is-loopback <host>
      Print ``true`` when ``host`` is a loopback address (empty, ``localhost``,
      ``::1`` or anything in ``127.0.0.0/8``), ``false`` otherwise.

This module is intentionally dependency-light: only PyYAML and the stdlib.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import re
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
    # HOST is the address ga-portal publishes on — loopback-only by default.
    "HOST": "127.0.0.1",
    "PORT": "64057",
    "GA_HOST_URL": "",
    "GA_API_KEY": "",
    "GA_TLS_CERTFILE": "",
    "GA_TLS_KEYFILE": "",
    "GA_TRUSTED_PROXY_CIDR": "",
    "GA_REQUIRE_SECRET_ON_EXTERNAL_BIND": "false",
    # ── crew lifecycle ──
    "GA_MAX_CREWS": "20",
    "GA_MAX_ACTIVE_CREWS": "3",
    "GA_IDLE_TIMEOUT_SECS": "300",
    "GA_SUBAGENT_TIMEOUT_SECS": "3600",
    "GA_BATCH_MAX_TASKS": "20",
    "GA_PICKUP_MAX_POLL_SECS": "30",
    # ── memory gate ──
    "GA_MIN_FREE_MEM_GB": "2.0",
    "GA_SPAWN_MIN_MEMORY_GB": "1.5",
    "GA_RESOURCE_PRESSURE_GB": "2.0",
    "GA_RESOURCE_CRITICAL_GB": "1.0",
    "GA_SPAWN_PRESSURE_ESCALATE_CYCLES": "3",
    # ── model (global fallback only; no global override — TRN-257) ──
    "KC_MODEL_DEFAULT": "",
    # ── git identity ──
    "GA_GIT_AUTHOR_NAME": "",
    "GA_GIT_AUTHOR_EMAIL": "",
    # ── backends ──
    "GA_CREW_AGENT": "kiro",
    "KIRO_IDENTITY_PROVIDER": "",
    "KIRO_REGION": "",
    "ANTHROPIC_BASE_URL": "",
    "OPENAI_BASE_URL": "",
    # ── per-backend model control (TRN-257) ──
    "KC_MODEL_KIRO_OVERRIDE": "",
    "KC_MODEL_KIRO_DEFAULT": "",
    "KC_MODEL_CLAUDE_OVERRIDE": "",
    "KC_MODEL_CLAUDE_DEFAULT": "",
    "KC_MODEL_CODEX_OVERRIDE": "",
    "KC_MODEL_CODEX_DEFAULT": "",
    # ── user-defined orders ──
    "GA_ORDERS_DIR": "",
    # ── images (advanced) ──
    "PODMAN_SOCKET": "/run/user/1000/podman/podman.sock",
    "KC_IMAGE": "localhost/spec-ops:latest",
    "KC_BASE_IMAGE": "",
    # Pin for mcteamstar/.agents baked into the crew image (TRN-264).
    # Empty = use the Containerfile default ("main") — override with a tag or
    # SHA for reproducible builds. A changed value forces a crew image rebuild.
    "AGENTS_REF": "",
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
    ("network", "tls", "certfile"): "GA_TLS_CERTFILE",
    ("network", "tls", "keyfile"): "GA_TLS_KEYFILE",
    ("network", "trusted_proxy_cidr"): "GA_TRUSTED_PROXY_CIDR",
    ("network", "require_secret_on_external_bind"): "GA_REQUIRE_SECRET_ON_EXTERNAL_BIND",
    # crew
    ("crew", "max_crews"): "GA_MAX_CREWS",
    ("crew", "max_active"): "GA_MAX_ACTIVE_CREWS",
    ("crew", "idle_timeout_secs"): "GA_IDLE_TIMEOUT_SECS",
    ("crew", "subagent_timeout_secs"): "GA_SUBAGENT_TIMEOUT_SECS",
    ("crew", "batch_max_tasks"): "GA_BATCH_MAX_TASKS",
    ("crew", "pickup_max_poll_secs"): "GA_PICKUP_MAX_POLL_SECS",
    ("crew", "orders_dir"): "GA_ORDERS_DIR",
    ("crew", "git", "author", "name"): "GA_GIT_AUTHOR_NAME",
    ("crew", "git", "author", "email"): "GA_GIT_AUTHOR_EMAIL",
    # crew.memory
    ("crew", "memory", "min_free_mem_gb"): "GA_MIN_FREE_MEM_GB",
    ("crew", "memory", "spawn_min_memory_gb"): "GA_SPAWN_MIN_MEMORY_GB",
    ("crew", "memory", "resource_pressure_gb"): "GA_RESOURCE_PRESSURE_GB",
    ("crew", "memory", "resource_critical_gb"): "GA_RESOURCE_CRITICAL_GB",
    ("crew", "memory", "spawn_pressure_escalate_cycles"): "GA_SPAWN_PRESSURE_ESCALATE_CYCLES",
    # model (global fallback only — no global override as of TRN-257)
    ("model", "default"): "KC_MODEL_DEFAULT",
    # backends
    ("backends", "default"): "GA_CREW_AGENT",
    ("backends", "kiro", "identity_center", "url"): "KIRO_IDENTITY_PROVIDER",
    ("backends", "kiro", "identity_center", "region"): "KIRO_REGION",
    ("backends", "claude", "base_url"): "ANTHROPIC_BASE_URL",
    ("backends", "codex", "base_url"): "OPENAI_BASE_URL",
    # per-backend model control (TRN-257)
    ("backends", "kiro", "model", "override"): "KC_MODEL_KIRO_OVERRIDE",
    ("backends", "kiro", "model", "default"): "KC_MODEL_KIRO_DEFAULT",
    ("backends", "claude", "model", "override"): "KC_MODEL_CLAUDE_OVERRIDE",
    ("backends", "claude", "model", "default"): "KC_MODEL_CLAUDE_DEFAULT",
    ("backends", "codex", "model", "override"): "KC_MODEL_CODEX_OVERRIDE",
    ("backends", "codex", "model", "default"): "KC_MODEL_CODEX_DEFAULT",
    # portal
    ("portal", "tls_mode"): "GA_PORTAL_TLS_MODE",
    ("portal", "domain"): "GA_PORTAL_DOMAIN",
    ("portal", "session_ttl_secs"): "GA_PORTAL_SESSION_TTL_SECS",
    ("portal", "dashboard", "port_range", "start"): "GA_DASHBOARD_PORT_RANGE_START",
    ("portal", "dashboard", "port_range", "size"): "GA_DASHBOARD_PORT_RANGE_SIZE",
    ("portal", "dashboard", "default"): "GA_DASHBOARD_DEFAULT",
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
    ("machine", "resources", "cpus"): "GA_MACHINE_CPUS",
    ("machine", "resources", "memory_mb"): "GA_MACHINE_MEMORY",
    ("machine", "resources", "disk_gb"): "GA_MACHINE_DISK",
    # machine.images (was top-level images: — merged into machine, TRN-257)
    ("machine", "images", "podman_socket"): "PODMAN_SOCKET",
    ("machine", "images", "kc_image"): "KC_IMAGE",
    ("machine", "images", "kc_base_image"): "KC_BASE_IMAGE",
    ("machine", "images", "agents_ref"): "AGENTS_REF",
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
        "KIRO_LICENSE",
    }
)


# ── Deprecated YAML path rewrite (TRN-257) ────────────────────────────────────
# TRN-257 restructured the YAML into logical sub-sections. Operators with a
# ghostship.yaml written against the TRN-253 flat layout are supported: each old
# tuple-path is rewritten to its new path on load, with a warning. The special
# case `("model", "override")` has no replacement — the global override was
# removed as a cross-backend footgun — so it is warned and discarded.
#
# Order matters only in that `_DISCARDED_YAML_PATHS` paths are dropped, never
# copied. Every entry here maps an OLD path to its NEW path.
_DEPRECATED_YAML_PATHS: dict[tuple[str, ...], tuple[str, ...]] = {
    ("network", "tls_certfile"): ("network", "tls", "certfile"),
    ("network", "tls_keyfile"): ("network", "tls", "keyfile"),
    ("crew", "git_author_name"): ("crew", "git", "author", "name"),
    ("crew", "git_author_email"): ("crew", "git", "author", "email"),
    ("backends", "agent"): ("backends", "default"),
    ("backends", "kiro", "identity_provider"): ("backends", "kiro", "identity_center", "url"),
    ("backends", "kiro", "region"): ("backends", "kiro", "identity_center", "region"),
    ("portal", "dashboard_port_range_start"): ("portal", "dashboard", "port_range", "start"),
    ("portal", "dashboard_port_range_size"): ("portal", "dashboard", "port_range", "size"),
    ("portal", "dashboard_default"): ("portal", "dashboard", "default"),
    ("machine", "cpus"): ("machine", "resources", "cpus"),
    ("machine", "memory"): ("machine", "resources", "memory_mb"),
    ("machine", "disk"): ("machine", "resources", "disk_gb"),
    ("images", "podman_socket"): ("machine", "images", "podman_socket"),
    ("images", "kc_image"): ("machine", "images", "kc_image"),
    ("images", "kc_base_image"): ("machine", "images", "kc_base_image"),
}

# network.api_key is three-state (string key / unset / false opt-out), so it is
# flattened by _api_key_env rather than _normalise_scalar.
_API_KEY_PATH: tuple[str, ...] = ("network", "api_key")

# network.require_api_key was folded into network.api_key: false. It is still
# accepted (so it is not reported as unknown) but only ``off`` has an effect,
# and that is applied by install.sh after the full key resolution — a key from
# the --api-key flag or a persisted key must still win over it.
_REQUIRE_API_KEY_PATH: tuple[str, ...] = ("network", "require_api_key")

# Removed paths with no replacement — warn and discard.
_DISCARDED_YAML_PATHS: dict[tuple[str, ...], str] = {
    ("model", "override"): (
        "model.override has been removed — a global model override is a footgun "
        "across backends with different model namespaces. Use "
        "backends.<backend>.model.override instead (e.g. backends.kiro.model.override). "
        "The value is ignored."
    ),
    ("backends", "kiro", "license"): (
        "backends.kiro.license has been removed — the kiro-cli license flag is "
        "derived from the login method (identity-center => pro, builder-id => "
        "free). The value is ignored."
    ),
}


def _pop_path(tree: dict[str, Any], path: tuple[str, ...]) -> Any:
    """Remove and return the leaf at ``path`` in ``tree``, or ``_MISSING``.

    Prunes any intermediate dicts that become empty after the removal so a
    deprecated section (e.g. a lone top-level ``images:``) does not linger as an
    empty mapping and get reported as an unknown key.
    """
    # Walk to the parent, recording the chain so we can prune empties.
    chain: list[dict[str, Any]] = [tree]
    cursor: Any = tree
    for segment in path[:-1]:
        if not isinstance(cursor, dict) or segment not in cursor:
            return _MISSING
        cursor = cursor[segment]
        chain.append(cursor)
    leaf_key = path[-1]
    if not isinstance(cursor, dict) or leaf_key not in cursor:
        return _MISSING
    value = cursor.pop(leaf_key)
    # Prune now-empty parent dicts from the deepest upward.
    for depth in range(len(path) - 2, -1, -1):
        parent = chain[depth]
        key = path[depth]
        child = parent.get(key)
        if isinstance(child, dict) and not child:
            del parent[key]
    return value


def _set_path(tree: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    """Set the leaf at ``path`` in ``tree``, creating intermediate dicts."""
    cursor = tree
    for segment in path[:-1]:
        nxt = cursor.get(segment)
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[segment] = nxt
        cursor = nxt
    cursor[path[-1]] = value


def _rewrite_deprecated_yaml_paths(tree: dict[str, Any]) -> None:
    """Rewrite old TRN-253 YAML paths to their TRN-257 locations, in place.

    For each deprecated path present in ``tree``: if the new path is not already
    set, copy the value there; delete the old key; warn naming both paths. When
    the new path is already set (operator used both forms), the new value wins
    and no warning is emitted for the old key (it is simply removed).

    Removed paths (``_DISCARDED_YAML_PATHS``, e.g. ``model.override``) are warned
    about and discarded without a replacement.
    """
    for old_path, msg in _DISCARDED_YAML_PATHS.items():
        if _lookup_path(tree, old_path) is not _MISSING:
            _pop_path(tree, old_path)
            sys.stderr.write(f"warning: {msg}\n")

    for old_path, new_path in _DEPRECATED_YAML_PATHS.items():
        old_value = _pop_path(tree, old_path)
        if old_value is _MISSING:
            continue
        old_dotted = ".".join(old_path)
        new_dotted = ".".join(new_path)
        if _lookup_path(tree, new_path) is not _MISSING:
            # New path already set — it wins; old key already removed above.
            continue
        _set_path(tree, new_path, old_value)
        sys.stderr.write(
            f"warning: config key '{old_dotted}' is deprecated; "
            f"use '{new_dotted}' instead (value applied).\n"
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
        value: Any = DEFAULTS[env]
        # backends.default is canonically a YAML list; the DEFAULTS table stores
        # the comma-string form "kiro" for GA_CREW_AGENT, so expand it to a list
        # here. This keeps flatten_to_env on the list path (no spurious
        # string-deprecation warning on an unconfigured install).
        if path == ("backends", "default"):
            value = [p for p in str(value).split(",") if p]
        cursor = tree
        for segment in path[:-1]:
            cursor = cursor.setdefault(segment, {})
        cursor[path[-1]] = value
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
        layer = load_yaml(explicit_path)
        _rewrite_deprecated_yaml_paths(layer)
        merged = deep_merge(merged, layer)
    else:
        repo_layer = load_yaml(repo_path)
        _rewrite_deprecated_yaml_paths(repo_layer)
        merged = deep_merge(merged, repo_layer)
        xdg_layer = load_yaml(xdg_path)
        _rewrite_deprecated_yaml_paths(xdg_layer)
        merged = deep_merge(merged, xdg_layer)
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
        if path == ("backends", "default"):
            env[var] = _normalise_backends_default(value)
            continue
        if path == _API_KEY_PATH:
            continue  # three-state; handled by _api_key_env below
        env[var] = _normalise_scalar(value)
    env.update(_api_key_env(_lookup_path(merged, _API_KEY_PATH)))
    env.update(_require_api_key_env(_lookup_path(merged, _REQUIRE_API_KEY_PATH)))
    return env


def _api_key_env(value: Any) -> dict[str, str]:
    """Flatten the three-state ``network.api_key``.

    A non-empty string enables auth with that key; ``false`` is the explicit
    opt-out; absent, ``null`` or ``""`` is unset. ``null`` deliberately means
    unset — ``api_key:`` with nothing after it is an easy accident and must
    never disable authentication. ``true`` and the strings ``"true"``/``"false"``
    are rejected so a quoted boolean is never used as a literal key.

    ``GA_API_KEY_SOURCE=yaml`` tells install.sh the YAML set the key (or the
    opt-out), so a previously persisted ``--api-key`` must not override it.
    """
    if value is _MISSING or value is None or value == "":
        return {"GA_API_KEY": "", "GA_API_KEY_DISABLED": "", "GA_API_KEY_SOURCE": ""}
    if value is False:
        return {"GA_API_KEY": "", "GA_API_KEY_DISABLED": "true", "GA_API_KEY_SOURCE": "yaml"}
    if isinstance(value, str) and value.strip().lower() not in ("true", "false"):
        return {"GA_API_KEY": value, "GA_API_KEY_DISABLED": "", "GA_API_KEY_SOURCE": "yaml"}
    raise ValueError(
        "network.api_key must be a non-empty string (the API key), false "
        f"(explicitly disable authentication), or unset — got {value!r}"
    )


def _require_api_key_env(value: Any) -> dict[str, str]:
    """Map the deprecated ``network.require_api_key`` with a warning.

    Only ``off`` has an effect: it becomes ``GA_API_KEY_DEPRECATED_OFF=true``,
    which install.sh treats as the opt-out only when no key was resolved from
    any source. ``error`` and ``warn`` are ignored (an unset key on a
    non-loopback install now always aborts).
    """
    if value is _MISSING or value is None:
        return {}
    setting = _normalise_scalar(value).strip().lower()
    if setting == "off":
        sys.stderr.write(
            "warning: network.require_api_key is deprecated; use "
            "network.api_key: false instead (treated as that when no API key is set).\n"
        )
        return {"GA_API_KEY_DEPRECATED_OFF": "true"}
    sys.stderr.write(
        f"warning: network.require_api_key is deprecated and '{setting}' is ignored; "
        "set network.api_key to a key, or network.api_key: false to opt out.\n"
    )
    return {}


def is_loopback(host: str) -> bool:
    """True for an unset host, ``localhost``, ``::1`` and ``127.0.0.0/8``.

    Mirrors ``transport.config.is_loopback`` — install.sh calls this through the
    ``is-loopback`` subcommand so the install-time and startup checks agree.
    """
    host = (host or "").strip()
    if not host or host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def _normalise_backends_default(value: Any) -> str:
    """Normalise ``backends.default`` to the comma-string ``GA_CREW_AGENT`` wants.

    The canonical form is a YAML list (``[kiro, claude]`` -> ``"kiro,claude"``).
    A bare string is the deprecated TRN-253 form (``backends.agent: "kiro"``);
    it is accepted as-is with a deprecation warning. Any other scalar is coerced
    through ``_normalise_scalar`` for robustness.
    """
    if isinstance(value, list):
        return ",".join(_normalise_scalar(item) for item in value)
    if isinstance(value, str):
        sys.stderr.write(
            "warning: backends.default as a string is deprecated; "
            "use a YAML list instead (e.g. backends.default: [kiro, claude]).\n"
        )
        return value
    return _normalise_scalar(value)


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
            if here in _KEY_MAP or here == _REQUIRE_API_KEY_PATH:
                continue  # mapped leaf (or deprecated-but-accepted)
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

    # GA_REQUIRE_API_KEY=off becomes network.api_key: false — but only when the
    # conf sets no key of its own; any other value is dropped.
    conf_values = dict(pairs)
    if (
        conf_values.get("GA_REQUIRE_API_KEY", "").strip().lower() == "off"
        and not conf_values.get("GA_API_KEY", "")
    ):
        _set_path(tree, _API_KEY_PATH, False)

    for key, value in pairs:
        env = _DEPRECATED_CONF_ALIASES.get(key, key)
        if env in _DROPPED_CONF_KEYS or key in _DROPPED_CONF_KEYS:
            continue
        if key == "GA_REQUIRE_API_KEY":
            continue  # handled above
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


_SAFE_KEY_RE = re.compile(r"^[A-Z0-9_]+$")


def _cmd_resolve(args: argparse.Namespace) -> int:
    merged = resolve_config(
        repo_path=args.repo or "",
        xdg_path=args.xdg or "",
        explicit_path=args.config or None,
    )
    for path in collect_unknown_paths(merged):
        sys.stderr.write(f"warning: unknown config key '{path}' ignored\n")
    try:
        env = flatten_to_env(merged)
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    for key in sorted(env):
        if not _SAFE_KEY_RE.match(key):
            sys.stderr.write(
                f"error: unsafe key name {key!r} — "
                "keys must match [A-Z0-9_]+; aborting to prevent shell injection\n"
            )
            return 1
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


def _cmd_is_loopback(args: argparse.Namespace) -> int:
    sys.stdout.write("true\n" if is_loopback(args.host) else "false\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if not (argv and argv[0] == "is-loopback"):
        _require_yaml()  # is-loopback is stdlib-only
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

    p_loop = sub.add_parser("is-loopback", help="print true if HOST is a loopback address")
    p_loop.add_argument("host", nargs="?", default="", help="host address (empty = unset)")
    p_loop.set_defaults(func=_cmd_is_loopback)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
