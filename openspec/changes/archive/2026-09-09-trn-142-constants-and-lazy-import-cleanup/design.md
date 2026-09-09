## Context

See proposal.md — Why.

The codebase has two independent cleanup targets:

1. **Constant fragmentation**: `CREW_GATEWAY_PORT`, `CREW_CONTAINER_PREFIX`, `CREW_VOLUME_PREFIX`, `CREW_HOME_VOLUME_PREFIX`, `GA_PORTSIDE_NETWORK`, `GA_STARBOARD_NETWORK`, `PERSONA_NAMES`, `SCRIPTS_DIR` are each declared in multiple modules. `lifecycle.py` is the current informal home for most of them but not all. `monitors.py` receives `CREW_GATEWAY_PORT` via `bind_lifecycle()` injection rather than importing it directly, to break a load-time cycle that no longer exists.

2. **`files.py` lazy-import dead code**: `_crew_helpers()` at line 107 resolves `_ensure_crew_running` and `_require_crew` lazily, first from `lifecycle`, then falling back to `server` if that fails. The fallback was needed during TRN-71 step 5; step 5 is complete and the fallback path has not been exercised since.

## Goals / Non-Goals

**Goals:**
- Single canonical import path for every container-side constant
- Direct import replaces the `bind_lifecycle()` injection for `CREW_GATEWAY_PORT` in `monitors.py`
- Remove `_crew_helpers()` and its `server.py` fallback from `files.py`
- All tests continue to pass with no behaviour change

**Non-Goals:**
- Not moving Config fields or env-var names into constants.py (they belong in config.py)
- Not addressing the `Config.from_env()` called 7× pattern (separate concern)
- Not touching constant names or values

## Decisions

### D1: New leaf module `transport/constants.py` rather than promoting `lifecycle.py` as the canonical source

`lifecycle.py` already re-exports most constants but it is a large, heavyweight module. Making it the canonical source means every module that only needs `CREW_GATEWAY_PORT` transitively imports the entire lifecycle module. A dedicated `constants.py` with zero transport imports keeps the dependency graph clean and is safe to import from any module including `podman.py` and `captain.py` which currently cannot import from `lifecycle.py` without creating cycles.

Alternative considered: use `lifecycle.py` as-is and just remove the duplicates in `server.py` and `podman.py`. Rejected — does not solve the `monitors.py` injection issue and leaves a heavyweight import for modules that only need constants.

### D2: Keep `lifecycle.py` re-exporting the constants it currently re-exports

`server.py` and tests reference `lifecycle.GA_PORTSIDE_NETWORK`, `lifecycle.CREW_GATEWAY_PORT` etc. via the existing re-exports. Preserving the re-exports avoids a large patch surface; they become one-line `from transport.constants import ...` at the top of `lifecycle.py`. Removing them entirely is a follow-on clean-up (TRN-143 or later).

### D3: Replace `bind_lifecycle()` injection in `monitors.py` with a direct import

The injection mechanism in `monitors.py` originally existed to break a lifecycle → monitors → lifecycle load-time cycle. `CREW_GATEWAY_PORT` is not part of that cycle — it is a plain integer constant with no transport dependencies. Safe to import directly from `constants.py`.

### D4: Replace `_crew_helpers()` with a direct `lifecycle` import at module level in `files.py`

Confirm the fallback is unreachable by checking test coverage and import order, then remove it. The direct `from transport.lifecycle import _ensure_crew_running, _require_crew` import already works in all test paths (the lifecycle branch in `_crew_helpers()` has been the active path since TRN-71).

## Risks / Trade-offs

- [Tests patch `lifecycle.CREW_GATEWAY_PORT` or `server.CREW_GATEWAY_PORT`] → After migration, the canonical patch target is `transport.constants.CREW_GATEWAY_PORT`. Tests that patch the old locations will still work if the re-exports remain (patching the re-export patches the name in that module's namespace, not the source). Audit and update any test that patches the constant to use the canonical location.
- [Circular import introduced by `constants.py`] → Zero risk: `constants.py` has no transport imports by definition.
- [`_crew_helpers()` removal breaks a test setup path] → Mitigated by running the full suite before committing. The server.py fallback has not been exercised since TRN-71; grep confirms no test explicitly triggers it.

## Migration Plan

1. Create `transport/constants.py` with all constants
2. Update `lifecycle.py` — replace declarations with `from transport.constants import ...`, keep re-exports
3. Update `server.py` — remove duplicate declarations, import from constants where needed
4. Update `podman.py`, `captain.py` — remove local declarations, import from constants
5. Update `monitors.py` — remove `bind_lifecycle()` CREW_GATEWAY_PORT injection, import from constants
6. Update `files.py` — remove `_crew_helpers()`, add direct lifecycle import
7. Run full test suite; fix any patching targets that need updating
8. Commit as a single atomic change

Rollback: revert the commit. No data migration, no protocol change, no deploy step needed.
