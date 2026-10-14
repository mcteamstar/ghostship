# Proposal

**Plane ticket:** TRN-240

## Why

The transport has grown organically into a procedural codebase. `server.py` (5128 lines) and `lifecycle.py` (4239 lines) are flat collections of module-level functions sharing state through a global registry dict. The domain has clear objects — crews, login flows, the registry, the Podman client — but none of them are modelled as classes. Everything is a function that takes a `crew` dict and threads it through manually.

The result: functions that should be methods are scattered across files, shared state leaks through global variables, and adding a feature means finding the right place in a 5000-line file rather than extending a coherent object.

## What Changes

Identify the natural objects in the transport domain and give them classes. The goal is not file splitting for its own sake — it's finding the right encapsulation boundaries so that code is grouped by what it *is*, not just what it *does*.

### Natural objects to model

**`Crew`** — the most obvious missing class. Currently a raw `dict` passed everywhere. Should encapsulate its own state (`container_id`, `volume`, `gateway_url`, `last_task_at`, etc.), know how to serialise/deserialise itself from the registry, and own methods that operate purely on crew state (`is_idle()`, `is_warm()`, `gateway_url()`, `to_dict()`).

**`CrewRegistry`** — the global registry dict + lock is a data structure with operations. Should be a class: `get(crew_id)`, `put(crew_id, crew)`, `remove(crew_id)`, `list()`, `load()`, `save()`. Eliminates the pattern of `with _registry_lock: reg = _load_registry(); reg["crews"][crew_id] = ...` repeated everywhere.

**`CrewLauncher`** — the launch/setup/recovery sequence (`_ensure_crew_running`, `_finish_crew_setup`, `_phase0/1/2`, `_crew_api_with_recovery`) is a single conceptual operation — bring a crew to a ready state — fragmented across ~10 functions and 1000+ lines. A class with a `run()` method and private phase methods makes the state machine explicit.

**`LoginFlow`** — three near-identical login flows (kiro/claude/codex) share no base class. Each has initiate/poll/logout variants that are structurally identical. A base class with backend-specific subclasses eliminates the duplication and makes adding a fourth backend mechanical.

**`AcademyLoader`** — `_copy_agents`, `_copy_skills`, `_copy_steering`, `_copy_policies` are the same function four times with a different directory name. One class with a parameterised `copy(kind)` method.

### What stays as functions

Not everything needs to be a class. Pure utility functions (`_validate_model`, `_sanitise_query_string`, `_jwt_exp`), one-off helpers, and route handlers that are genuinely stateless can stay as functions. The goal is not to wrap everything in a class — it's to find the objects that *have* identity and state, and model them properly.

## Non-Goals

- No behaviour or API changes — all MCP tools and REST endpoints unchanged
- No new features
- File organisation is a secondary outcome, not the primary goal

## Impact

- `transport/` — new classes, likely new modules as a natural consequence of the class extraction
- All existing tests must pass unchanged; new tests for extracted classes
- `docs/architecture.md` updated to reflect new class model
