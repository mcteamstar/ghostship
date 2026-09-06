## Context

See `proposal.md` — Why for the motivation.

The transport package currently has this module dependency graph:

```
config, registry, podman, captain, files   ← no transport imports
      ↓
  lifecycle  (imports config, registry, podman, captain, academy)
      ↓
  server     (imports lifecycle + all of the above)
```

`server.py` is the entry point: Uvicorn loads it, and it constructs the ASGI app. `lifecycle.py` owns crew start/stop/recovery and the idle/schedule monitors; `server.py` owns MCP tool handler definitions, HTTP middleware, Caddy management, and the login PTY flow. Neither `lifecycle.py` nor the lower-level modules import from `server.py`, so the dependency graph is acyclic today.

The container deployment also runs files flat under `/app` (not as a package), so imports use a `try/except ImportError` dual-path pattern (`from lifecycle import X` / `from transport.lifecycle import X`). Any new modules must preserve this pattern.

## Goals / Non-Goals

**Goals:**
- Reduce `server.py` and `lifecycle.py` to files that are navigable without scrolling through unrelated concerns
- Remove dead code (`_inject_git_identity`, `KIROCREW_ALLOW_UNSANDBOXED`) that misleads readers
- Consolidate repeated patterns (auth header parsing, registry lock usage) so fixes propagate from one place
- Improve internal documentation for complex state machines so mutation testing becomes practical
- Fill two specific test coverage gaps from the 0.3.0 review

**Non-Goals:**
- Changing any externally observable behaviour (API surface, container interaction, registry schema)
- Rewriting or redesigning the three-phase recovery logic — the current logic is correct, just hard to follow
- Extracting modules that would require non-trivial refactoring of the dual-path import pattern
- Touching `files.py`, `config.py`, `registry.py`, `podman.py`, or `captain.py` except where a targeted deduplication step reaches into them

## Decisions

### D-1: Modularisation scope — defer large extractions, do targeted ones only

**Decision**: For this cleanup cycle, extract modules only where the content is already cohesive and the dual-path import update is mechanical. Specifically:
- `transport/auth.py` — the three middleware classes (`TransportSecretMiddleware`, `BearerAuthMiddleware`, `SecurityHeadersMiddleware`) and the auth header parse helper. These classes have no outbound calls to `lifecycle.py` and are fully self-contained.
- `transport/caddy.py` — `_caddy_register_crew`, `_caddy_deregister_crew`, `_allocate_dashboard_port`, `_release_dashboard_port`, `_caddy_admin_url`. These make HTTP calls via `httpx` and reference `_registry_lock` from `lifecycle.py`; the import structure is clean.
- `transport/monitors.py` — `_schedule_monitor`, `_idle_monitor`, and their helpers (`_cron_activity_since`, `_cron_has_enabled_job`). These live in `lifecycle.py` but only call back into `lifecycle.py` via `_crew_api_with_recovery` and `_ensure_crew_running`; no import cycle risk.

**Deferred**: Extracting MCP tool handlers from `server.py` is the largest reduction but also the highest risk — each handler references globals defined in `server.py` (config values, lock objects, the `podman` instance). Untangling those globals into a shared state module is a 0.4.0 task, not a cleanup-pass task.

**Rationale**: The dual-path import pattern means every new module needs a matching `try/except` block in each consumer. Limiting extractions to self-contained units keeps the diff reviewable and the mocking surface in tests predictable.

**Alternative considered**: Extract everything in one go. Rejected — the test mock paths (`server._crew_api_with_recovery`, etc.) would all change simultaneously, making the diff large and the failure modes hard to isolate.

### D-2: Dead code removal — remove `_inject_git_identity` body and `KIROCREW_ALLOW_UNSANDBOXED`

**Decision**: Remove the function body of `_inject_git_identity` entirely (not just stub it) and remove the `KIROCREW_ALLOW_UNSANDBOXED` env-var injection from `server.py`.

**Rationale**: `_inject_git_identity` has an extensive docstring explaining why it was neutered; the call site in `_finish_crew_setup` still passes through it. Once removed, the docstring explains a past decision — it is better to convert it to a code comment at the call site noting that the vars are now injected at container-create time. `KIROCREW_ALLOW_UNSANDBOXED` is redundant per FINDING-3; its only reference in `server.py` is in the `launch` handler.

**Risk**: Low — `_inject_git_identity` is a no-op by definition. `KIROCREW_ALLOW_UNSANDBOXED` is injected into the container env during launch; removing it only affects a code path the `sandbox: off` config already subsumes.

### D-3: Deduplication — auth header parsing extracted to a single helper

**Decision**: Add a `_parse_bearer_token(header_value: str) -> str | None` helper (in `auth.py` if that module is created, otherwise inline in `server.py`) and replace the two inline `[:7].lower() == "bearer "` checks with calls to it.

**Rationale**: The current duplication is two places; extracting now sets the precedent so future additions don't add a third.

**Alternative considered**: Leave as-is since there are only two sites. Rejected — each site has slightly different whitespace handling; a single helper removes the inconsistency.

### D-4: `_crew_api_with_recovery` — phase extraction, not rewrite

**Decision**: Extract each phase of `_crew_api_with_recovery` into a private helper (`_phase0_transient_503`, `_phase1_stale_cookie`, `_phase2_dead_gateway`) and add a phase-label comment to the orchestrating function. Do not restructure the exception handling flow.

**Rationale**: The existing nested try/except structure is correct. The readability and testability problem is that the three phases are not visually distinct. Extracting phases into helpers with typed signatures makes the state machine explicit and lets mutation tests target each phase independently without needing to construct the full exception path.

**Alternative considered**: Replace nested try/except with a sentinel-return pattern. Rejected — changes the observable exception types and would require updating test assertions.

### D-5: Test additions — scope to two identified gaps only

**Decision**: Add tests for (a) `_handle_crew_ui_proxy` returning a non-2xx response from the upstream crew gateway, and (b) the dashboard URL when Caddy TLS is off. No other new tests in this pass.

**Rationale**: These were specifically called out in the 0.3.0 review. Broader coverage improvements belong to a dedicated test-coverage change, not a cleanup pass.

## Risks / Trade-offs

- **Mock path churn** → If modules are extracted, every `patch("server._crew_api_with_recovery", ...)` in the test suite must become `patch("lifecycle._crew_api_with_recovery", ...)` (or the new module path). Mitigation: run the full test suite after each extraction, fix mock paths before merging.

- **Circular imports** → Any new module that imports from `lifecycle.py` and is then imported back by `lifecycle.py` would create a cycle. Mitigation: the rule for new modules is strict — they may import from the leaf modules (`config`, `registry`, `podman`) but not from `lifecycle` or `server`. The monitors module is the exception; it imports from `lifecycle` and is imported only by `server`, maintaining the acyclic property.

- **Dual-path import boilerplate** → Each new module doubles the import surface (flat `/app` path + `transport.*` path). Mitigation: keep new modules to the minimum identified in D-1; document the pattern once in a module-level comment so future authors can follow it mechanically.

- **`_inject_git_identity` docstring loss** → The long docstring explains a subtle behaviour (why `/etc/environment` writes don't work for non-login processes). Mitigation: the key fact (vars injected at container-create time via `container_create env=`) is preserved as a comment at the `_finish_crew_setup` call site.

## Migration Plan

Each sub-task below is independently mergeable to `release/0.3.1`:

1. Dead code removal (`_inject_git_identity` body, `KIROCREW_ALLOW_UNSANDBOXED`) — no mock path changes
2. Auth header parse helper deduplication — no module moves
3. `_crew_api_with_recovery` phase extraction — no module moves
4. Extract `transport/auth.py` (middleware classes) — update mock paths in `test_server.py`
5. Extract `transport/caddy.py` — update mock paths in `test_server.py`
6. Extract `transport/monitors.py` — update mock paths in `test_lifecycle.py`
7. Add `_handle_crew_ui_proxy` upstream error tests
8. Add Caddy-off TLS dashboard URL tests

Tasks 1–3 carry zero circular-import risk and are the recommended starting point. Tasks 4–6 each involve a module move with test mock updates; do them in separate PRs so any import problem is isolated to a single extraction.

## Open Questions

- **Registry lock documentation**: The `_registry_lock` usage convention (C-1: acquire, mutate, release, then call Caddy outside the lock) is documented by comment at each site. Is a single authoritative comment block at the lock definition sufficient, or does the project prefer a brief `locking.md` doc? This is a style question that does not affect task scope.
