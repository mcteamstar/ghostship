## Why

`transport/lifecycle.py` is 1842 lines — the largest module in the transport package after TRN-71's extraction. A discovery pass (trn-layout-discovery) identified one clean extraction opportunity: the composition registry and crew manifest helpers form a distinct logical cluster with no upward dependencies within lifecycle.

These functions answer a single question: "what academy compositions exist, what do their manifests contain, and how do we validate what the academy directory holds?" That is a different concern from crew lifecycle management (launch, recovery, auth injection, monitoring). Giving it its own module makes the transport package's structure self-documenting.

This is the prerequisite for TRN-85 (test suite modularisation), which needs a `test_academy.py` target to map the academy tests to.

## What Changes

Extract nine functions and one constant from `transport/lifecycle.py` into a new `transport/academy.py` module (~360 lines). `lifecycle.py` shrinks from ~1842 to ~1500 lines.

**Extracted to `transport/academy.py`:**
- `COMPOSITION_REGISTRY` (module-level dict)
- `_load_composition_registry()`
- `_resolve_composition()`
- `_resolve_manifest_path()`
- `_resolve_image()`
- `_load_crew_manifest()`
- `_manifest_selects()`
- `_substitute_env_vars()`
- `_validate_academy()`

`server.py` and `lifecycle.py` import from `academy` using the same try/except fallback pattern used for other modules.

## Capabilities

No capability changes — pure structural refactor. `skip_specs: true` declared.

## Impact

- `transport/academy.py` — new file
- `transport/lifecycle.py` — ~340 lines removed
- `transport/server.py` — import block updated
- `tests/unit/test_transport.py` — patch targets for academy functions updated to `transport.academy` (or left for TRN-85)
- `transport/Containerfile` — no change (`COPY . /app/` already copies the full package)
