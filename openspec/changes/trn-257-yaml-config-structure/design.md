# Design

## Context

`yaml_config.py` has a single `_KEY_MAP` dict mapping YAML tuple-paths to env var names. Restructuring the YAML paths means updating those tuples. The env var names are untouched — `Config.from_env()` in the transport is not touched for existing keys.

New per-backend model keys (`backends.<b>.model.override` and `backends.<b>.model.default`) require new env vars and new `Config` fields, since the transport needs to resolve the precedence chain at spawn time. These are additive changes to the transport.

The `images` section merges into `machine.images` — path change only, env vars unchanged.

`model.override` is removed entirely. Existing `ghostship.yaml` files that set it get a warning and the value is ignored.

## Goals / Non-Goals

**Goals:** Restructure YAML paths for semantic clarity; add per-backend model knobs; merge `images` into `machine`; backwards-compatible load of old paths with warnings.

**Non-Goals:** Changing existing env var names, adding new config sections, changing `model.default` semantics.

## Decisions

**D1: Deprecated YAML path handling via a pre-flatten rewrite pass.**

After merging all layers into a tree, `_rewrite_deprecated_yaml_paths(tree)` walks a table of `(old_path, new_path)` pairs. For each old path found: copy value to new path (if not already set there), delete old key, print warning. Special case: `model.override` has no new path — warn and discard. Runs once on the merged tree before `flatten_to_env`.

**D2: `backends.default` list → comma-string join.**

In `flatten_to_env`, when resolving `("backends", "default")`: if the value is a list, join with `,`. If it's a string, use as-is with a deprecation warning (string was the old form from TRN-253).

**D3: Per-backend model env vars keyed by backend name.**

New env vars: `KC_MODEL_KIRO_OVERRIDE`, `KC_MODEL_KIRO_DEFAULT`, `KC_MODEL_CLAUDE_OVERRIDE`, `KC_MODEL_CLAUDE_DEFAULT`, `KC_MODEL_CODEX_OVERRIDE`, `KC_MODEL_CODEX_DEFAULT`. The transport resolves the precedence chain per backend at spawn time using these plus the existing `KC_MODEL_DEFAULT`.

Alternative considered: a single `KC_MODEL_BACKEND_CONFIG` JSON blob. Rejected — env vars are simpler to inspect, override at the shell level, and test.

**D4: `machine.images` path change, no env var change.**

`images.*` keys move to `machine.images.*` in `_KEY_MAP`. The env vars (`PODMAN_SOCKET`, `KC_IMAGE`, `KC_BASE_IMAGE`) are unchanged. Old `images.*` paths go through the deprecated-path rewrite pass.

**D5: Transport precedence logic.**

In `lifecycle.py` (or wherever model is resolved for a spawn), the chain becomes:
```python
model = (
    dispatch_model                        # from spawn request
    or cfg.kc_model_{backend}_override    # per-backend override
    or agent_model                        # from agent persona
    or cfg.kc_model_{backend}_default     # per-backend default
    or cfg.kc_model_default               # global default
    or BUILTIN_DEFAULT
)
```

**D6: docs/configuration.md.**

The "Model" section is rewritten to document the full precedence chain, explain when to use each level, and show examples. The old `model.override` entry is replaced with a migration note directing operators to per-backend overrides.

## Risks / Trade-offs

- **[Risk] Operator has `model.override` set** → Warned and ignored. They must migrate to `backends.<b>.model.override` for each backend they want to constrain.
- **[Risk] Operator has `images.*` keys** → Deprecated-path rewrite handles it transparently.
- **[Risk] Transport precedence change is a behaviour change** → Only affects installs that set the new per-backend model keys (none exist yet). Existing behaviour is preserved for all current keys.

## Migration Plan

No data migration. Existing `ghostship.yaml` files handled at load time by the rewrite pass. Deploy by running `ghostship upgrade` after merging.

## Open Questions

None.
