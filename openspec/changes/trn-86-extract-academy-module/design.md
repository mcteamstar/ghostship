## Context

`transport/lifecycle.py` contains 41 functions across six informal clusters. The discovery analysis (trn-layout-discovery/recommendation.md) confirmed that only one cluster can be cleanly extracted: the composition registry and manifest helpers. The cross-cutting glue functions (`_mint_cookie`, `_patch_crew_config`, `_wait_gateway`, `_probe_gateway`) prevent any other split.

## Decisions

### 1. What goes in academy.py

The extracted cluster answers: "what compositions and manifests does this academy install have, and is the academy directory valid?"

| Symbol | Type | Why it belongs here |
|:-------|:-----|:-------------------|
| `COMPOSITION_REGISTRY` | dict | The composition catalogue; populated at module load by `_load_composition_registry` |
| `_load_composition_registry` | fn | Reads `crews/registry.json`; populates `COMPOSITION_REGISTRY` |
| `_resolve_composition` | fn | Looks up a composition by name in `COMPOSITION_REGISTRY` |
| `_resolve_manifest_path` | fn | Returns the path to a composition's `manifest.json` |
| `_resolve_image` | fn | Returns the image name for a composition |
| `_load_crew_manifest` | fn | Reads and parses a composition's manifest.json |
| `_manifest_selects` | fn | Tests whether a manifest selects a given item (agent/skill/steering) |
| `_substitute_env_vars` | fn | Substitutes `${VAR}` placeholders in MCP catalogue entries |
| `_validate_academy` | fn | Checks academy directory structure against composition manifests |

### 2. Import pattern

Follow the same try/except fallback used in all other extracted modules:

```python
try:
    from academy import (          # container: flat /app/
        COMPOSITION_REGISTRY,
        _load_composition_registry,
        ...
    )
except ImportError:
    from transport.academy import ( # local dev
        COMPOSITION_REGISTRY,
        _load_composition_registry,
        ...
    )
```

Both `lifecycle.py` (for `_copy_agents`, `_copy_skills`, `_copy_steering` which call `_load_crew_manifest` and `_manifest_selects`) and `server.py` (for `COMPOSITION_REGISTRY` in `resource_compositions`) import from `academy`.

### 3. Circular import check

`academy.py` imports only:
- stdlib (`json`, `os`, `pathlib`, `logging`)
- `config.Config` (already at the bottom of the dep graph)

It does NOT import from `lifecycle`, `server`, `registry`, `podman`, `captain`, or `files`. No circular import risk.

Callers of academy functions:
- `lifecycle._copy_agents/skills/steering` → calls `_load_crew_manifest`, `_manifest_selects`, `_substitute_env_vars`
- `lifecycle._validate_academy` → now just calls `academy._validate_academy` (or is moved entirely)
- `server.resource_compositions` → reads `COMPOSITION_REGISTRY`

### 4. COMPOSITION_REGISTRY population

`COMPOSITION_REGISTRY` is a module-level dict populated at import time by `_load_composition_registry()`. After extraction, `server.py` imports both `COMPOSITION_REGISTRY` and `_load_composition_registry` from `academy`. Tests that patch `COMPOSITION_REGISTRY` must patch `academy.COMPOSITION_REGISTRY` (and `server.COMPOSITION_REGISTRY` for server-side reads).

This is a TRN-85 concern — the dual-patch in existing tests remains until TRN-85 migrates them to `test_academy.py`.

### 5. One commit, tests must pass

Follow TRN-71's pattern: create `academy.py`, update imports in `lifecycle.py` and `server.py`, verify no circular imports, run `bash tests/run.sh --unit` (must pass), commit.

## Risks

- **`_validate_academy` false positive warnings** — The `._` macOS sidecar files in `academy/agents/` already produce false positive warnings (noted in TRN-71 session). This is pre-existing and not introduced by this change.
- **Test patch targets** — Tests that patch `lifecycle.COMPOSITION_REGISTRY` or `server.COMPOSITION_REGISTRY` will need updating. The dual-patch workaround from TRN-71 keeps them passing until TRN-85 fixes them properly. Do not update test patch targets in this change — leave that for TRN-85.
