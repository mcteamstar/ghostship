# Design

## Context

`yaml_config.py` has a single `_KEY_MAP` dict mapping YAML tuple-paths to env var names. Restructuring the YAML paths means updating those tuples. The env var names are untouched — `Config.from_env()` in the transport is not touched.

The `backends.default` list type requires a special case in `flatten_to_env`: when the resolved value is a Python list, join it with commas. When it is a string, use it as-is (deprecated form, with a warning).

Old paths need a deprecated-alias pass: before flattening, walk the merged tree for known old paths and rewrite them to their new equivalents, emitting a warning per remapping found.

## Goals / Non-Goals

**Goals:** Restructure YAML paths for semantic clarity. Backwards-compatible load of old paths with warnings.

**Non-Goals:** Changing env var names, touching the transport, adding new config keys, removing any keys.

## Decisions

**D1: Deprecated YAML path handling via a pre-flatten rewrite pass.**

After merging all layers into a tree, a `_rewrite_deprecated_yaml_paths(tree)` function walks a table of `(old_path_tuple, new_path_tuple)` pairs. For each old path found in the tree: copy its value to the new path (if not already set), delete the old key, and print a deprecation warning. This runs once on the merged tree before `flatten_to_env`.

Alternative considered: handle it in `_lookup_path` by falling back to old paths. Rejected — too implicit, makes the data flow hard to follow and warnings hard to emit cleanly.

**D2: `backends.default` list → string join in `_normalise_scalar`.**

`_normalise_scalar` currently rejects non-scalar values. Add a pre-normalise step in `flatten_to_env` specifically for the `backends.default` path: if the resolved value is a list, join with `,` before passing to `_normalise_scalar`. String values pass through unchanged (deprecated form).

**D3: Migration (`ghostship.conf` → `ghostship.yaml`) uses new paths.**

The migrator writes YAML using `_ENV_TO_PATH`, which derives from `_KEY_MAP`. Since `_KEY_MAP` now uses new paths, migrated files get new paths automatically. Old `ghostship.conf` files have their keys translated directly to new YAML paths — no intermediate old-path step needed.

## Risks / Trade-offs

- **[Risk] Operator has a `ghostship.yaml` using old paths** → Mitigation: deprecated-path rewrite pass warns and applies the value. No silent breakage.
- **[Risk] Both old and new path set in the same file** → New path wins (it is deeper in the merge, having been set after the rewrite pass normalises the old one). Documented in spec.

## Migration Plan

No data migration. Existing `ghostship.yaml` files using old paths are handled at load time by the rewrite pass. The wizard and migrator already write new paths. Deploy by running `ghostship upgrade` after merging.

## Open Questions

None.
