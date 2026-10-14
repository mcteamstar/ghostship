# Tasks

## 1. Crew dataclass

- [ ] 1.1 Create `transport/crew.py`. Define `Crew` as a `@dataclass` with all fields currently stored in the registry dict. Add `is_idle(timeout_secs)`, `is_warm()`, `to_dict()`, and `from_dict(cls, data)`. Add a unit test in `tests/unit/test_crew.py` covering round-trip serialisation and `is_idle`/`is_warm` logic. Verify: `Crew.from_dict(crew.to_dict()) == crew`.

- [ ] 1.2 Migrate `lifecycle.py` and `server.py` to use `Crew` objects instead of raw dicts at all internal call sites. The registry still serialises to JSON via `to_dict()`/`from_dict()` at load/save boundaries — no storage format change. Verify: `pytest tests/unit/ -q` green.

## 2. CrewRegistry class

- [ ] 2.1 Add `CrewRegistry` to `transport/crew.py` (or `transport/registry.py` if it already exists and is appropriate). Implement `get`, `put`, `remove`, `list`, `load`, `save`, and context-manager `__enter__`/`__exit__` for atomic read-modify-write. The context manager acquires the existing `_registry_lock` equivalent and calls `load()`/`save()` automatically. Add unit tests covering concurrent access, missing crew lookup returning `None`, and serialisation round-trip.

- [ ] 2.2 Replace all `with _registry_lock: reg = _load_registry(); ...; _save_registry(reg)` patterns in `lifecycle.py` and `server.py` with the `CrewRegistry` context manager. Keep `_load_registry` and `_save_registry` as private methods on the class. Verify: `pytest tests/unit/ -q` green.

## 3. AcademyLoader class

- [ ] 3.1 Add `AcademyLoader` to `transport/academy.py`. Implement `copy(kind: str) -> list[str]` and `copy_all() -> dict[str, list[str]]`. Replace the four functions `_copy_agents`, `_copy_skills`, `_copy_steering`, `_copy_policies` with calls to `AcademyLoader(podman, container, composition_entry).copy(kind)`. Add a unit test verifying that each kind calls the right source directory. Verify: `pytest tests/unit/ -q` green.

## 4. LoginFlow class hierarchy

- [ ] 4.1 Create `transport/login.py`. Define abstract base `LoginFlow` with `initiate`, `poll`, `logout`. Implement `KiroLoginFlow`, `ClaudeLoginFlow` (with `exchange_code`), `CodexLoginFlow` as subclasses. Extract the relevant functions from `server.py` into these classes. Route handlers in `server.py` become thin wrappers that instantiate the right subclass and call its methods. Add unit tests for each backend's initiate/poll/logout. Verify: `pytest tests/unit/ -q` green.

## 5. CrewLauncher class

- [ ] 5.1 Create `transport/launcher.py`. Define `CrewLauncher` with `ensure_running(crew_id) -> Crew` as the public method. Extract `_ensure_crew_running`, `_finish_crew_setup`, `_phase0_transient_503`, `_phase1_stale_cookie`, `_phase2_dead_gateway`, `_crew_api_with_recovery` from `lifecycle.py` as private methods. `CrewLauncher` takes `CrewRegistry`, `PodmanClient`, and `Config` in its constructor — no global state access. Add unit tests for each phase using mocked podman and registry. Verify: `pytest tests/unit/ -q` green.

## 6. Cleanup and docs

- [ ] 6.1 After all classes are in place, audit `server.py` and `lifecycle.py` for remaining duplication or dead code introduced during migration. Remove any functions that became unreachable. Verify line counts have meaningfully reduced and `pytest tests/unit/ -q` still green.

- [ ] 6.2 Update `docs/architecture.md` to document the new class model: `Crew`, `CrewRegistry`, `CrewLauncher`, `LoginFlow` hierarchy, `AcademyLoader`. Replace the current module-level function descriptions with class/method descriptions.

## Workflow follow-up

- Archive the change after review.
