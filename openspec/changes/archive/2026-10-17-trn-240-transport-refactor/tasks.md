# Tasks

Each task is scoped to one commit with tests green. No task leaves a broken
intermediate state. Tasks within a numbered group may be done in any order;
numbered groups must be done in order (each group's output is a prerequisite
for the next).

---

## 1. Atomic file write utility

- [x] 1.1  **Extract `_write_secret_file` utility.**
  In `transport/registry.py`, add a module-level function
  `_write_secret_file(path: Path, data: bytes | str) -> None` that performs the
  atomic 0600 write pattern (os.open with O_WRONLY|O_CREAT|O_TRUNC, 0o600 →
  fchmod → fdopen → write → fsync → os.chmod → dir fsync). Replace the three
  occurrences in `lifecycle.py` (`_write_auth_file` lines 2535–2554,
  `_write_claude_auth_file` lines 2571–2590, `_write_codex_auth_file`
  lines 3456–3475), the one in `registry.py` (`_write_crew_secret`
  lines 197–216), and the one in `registry.py` (`_save_registry` lines 72–92 —
  the open/fdopen/fsync block; `_save_registry` keeps its own logic but calls
  `_write_secret_file` for the actual fd operations).
  Test: add `test_write_secret_file_creates_with_mode_0600` in
  `tests/unit/test_registry.py`. Verify: `pytest tests/unit/ -q` green.

---

## 2. `Crew` dataclass

- [x] 2.1  **Create `transport/crew.py` with the `Crew` dataclass.**
  Fields: `crew_id: str`, `container: str`, `volume: str`, `home_volume: str`,
  `port: int = 5476`, `cookie: str = ""`, `internal_cookie: str = ""`,
  `status: str = "stopped"`, `composition: str = "spec-ops"`,
  `acp_backend: str = "kiro"`, `created_at: str = ""`, `last_used: float = 0.0`,
  `warm_until: float = 0.0` (in-memory only, excluded from `to_dict`),
  `enrolled_agents: list[str] = field(default_factory=list)`,
  `admiral_secret_id: str = ""`, `policy_version: str = ""`,
  `policy_signing_key_id: str = ""`, `crew_image_version: str = "unknown"`,
  `schedules: list[dict] = field(default_factory=list)`,
  `batches: list[dict] = field(default_factory=list)`.
  Implement `gateway_url()` → `f"http://{self.container}:{self.port}"`.
  Implement `is_idle(timeout_secs: int) -> bool` → `last_used > 0 and time.time() - last_used > timeout_secs`.
  Implement `is_warm() -> bool` → `time.monotonic() < self.warm_until`.
  Implement `to_dict() -> dict` — produce the same keys/values as the current
  `crew_entry` dict in `_finish_crew_setup` (lifecycle.py:2355–2394);
  `warm_until` is NOT included.
  Implement `from_dict(cls, crew_id: str, d: dict) -> "Crew"` — accept the
  current JSON shape, default unknown keys gracefully.
  Add `tests/unit/test_crew.py`: test round-trip `Crew.from_dict(crew_id, crew.to_dict()) == crew`,
  `is_idle` with times, `is_warm` with times, `gateway_url`. Verify: `pytest tests/unit/ -q` green.

- [x] 2.2  **Migrate crew dict accesses in `lifecycle.py` to use `Crew` objects.**
  Replace all `crew["container"]`, `crew.get("cookie", "")`, `crew["status"]`,
  etc. (19 accesses at lines ~330–1065 and ~1504–1535) with attribute access on
  a `Crew` instance. The load/save boundary: `_load_registry()` returns raw
  dicts; convert to `Crew` via `Crew.from_dict(cid, d)` immediately after load;
  `_save_registry()` call sites: write `crew.to_dict()` back. Replace the two
  inline uses of `_crew_url(crew)` and `_crew_cookie(crew)` with the dataclass
  methods. Verify: `pytest tests/unit/ -q` green.

- [x] 2.3  **Migrate crew dict accesses in `server.py` to use `Crew` objects.**
  Replace all 20 `crew["..."]` / `crew.get("...")` accesses (lines ~1087–4554).
  Where `server.py` constructs crew dicts inline (e.g. in the `launch` function
  body), replace with `Crew(...)` construction. Keep `_crew_url(crew)` and
  `_crew_cookie(crew)` calls working by delegating to `crew.gateway_url()` etc.
  Verify: `pytest tests/unit/ -q` green.

- [x] 2.4  **Migrate crew dict accesses in `files.py` to use `Crew` objects.**
  Replace all 12 `crew["container"]` / `crew.get(...)` accesses.
  `files.py` receives crew dicts from callers; update the relevant function
  signatures to accept `Crew` objects, and update their call sites in
  `server.py` accordingly. Verify: `pytest tests/unit/ -q` green.

---

## 3. `CrewRegistry` class

- [x] 3.1  **Add `CrewRegistry` to `transport/registry.py`.**
  Implement the class with `__init__(path: Path)`, context-manager
  `__enter__` / `__exit__` (acquire `_registry_lock`, load on enter, save on
  clean exit, release on exit), `get(crew_id) -> Crew | None`,
  `put(crew: Crew) -> None`, `remove(crew_id: str) -> None`,
  `list() -> list[Crew]`, `touch(crew_id: str) -> None`.
  The context manager saves only on clean exit (`exc_type is None`), never on
  exception — this prevents partial writes corrupting the registry.
  Add a module-level singleton `registry = CrewRegistry(REGISTRY_PATH)` at the
  bottom of `registry.py` (after the class definition) so import sites can
  use `from transport.registry import registry`.
  Add tests in `tests/unit/test_registry.py`: concurrent `put`/`get`, missing
  crew returns `None`, round-trip save/load, context-manager auto-save.
  Verify: `pytest tests/unit/ -q` green.

- [x] 3.2  **Migrate schedule and batch methods onto `CrewRegistry`.**
  Add `upsert_schedule`, `remove_schedule`, `get_schedules`, `advance_next_fire_at`,
  `write_batch`, `get_batch`, `update_batch_status`, `delete_batch`,
  `find_batch_by_task_ids` as methods. Each delegates to the existing
  `_upsert_crew_schedule`, `_write_batch`, etc. module-level functions — no
  logic duplication, just routing. Add `write_secret`, `read_secret`,
  `delete_secret` methods delegating to the existing `_write_crew_secret` etc.
  The existing module-level functions remain (as internal implementations) so
  monitors.py and tests that import them directly continue to work.
  Verify: `pytest tests/unit/ -q` green.

- [x] 3.3  **Migrate the 43 `with _registry_lock:` blocks in `server.py`.**
  Replace each `with _registry_lock: reg = _load_registry(); ...; _save_registry(reg)`
  block with a `with registry:` context manager call on the singleton, using
  `registry.get(cid)`, `registry.put(crew)`, `registry.remove(cid)`, etc.
  Focus first on the simplest cases (single get/put per block), then the
  compound read-modify-write blocks in `launch`, `nuke`, `crews`, `schedule`.
  Verify: `pytest tests/unit/ -q` green after each logical sub-group.

- [x] 3.4  **Migrate the 17 `with _registry_lock:` blocks in `lifecycle.py`.**
  Same pattern as 3.3. Key sites: `_refresh_cookie` (lines ~425–466),
  `_ensure_crew_running` (lines ~747–1065), `_finish_crew_setup`
  (lines ~2168–2408), `_reconcile_registry` (lines ~1769–1890).
  Verify: `pytest tests/unit/ -q` green.

- [x] 3.5  **Migrate the 13 `with _registry_lock:` blocks in `monitors.py`.**
  Monitors imports `_registry_lock`, `_load_registry`, `_save_registry`,
  `_touch_crew` directly from `registry`. After introducing the singleton,
  monitors can import `registry` from `registry` and call its methods instead.
  The `bind_lifecycle` injection for monitors does NOT need to include
  the registry singleton (monitors already imports from `registry` directly).
  Verify: `pytest tests/unit/ -q` green.

- [x] 3.6  **Migrate the 3 `with _registry_lock:` blocks in `captain.py`.**
  Same pattern. Verify: `pytest tests/unit/ -q` green.

---

## 4. `AcademyLoader` class

- [x] 4.1  **Add `AcademyLoader` to `transport/academy.py`.**
  Implement `AcademyLoader(podman, container, composition_entry=None)` with
  `copy(kind: str) -> list[str]` and `copy_all() -> dict[str, list[str]]`.
  `copy("agents")` runs the body of `_copy_agents` (lifecycle.py:1217–1308),
  including the mcp.json write logic. `copy("skills")` runs `_copy_skills`
  (lifecycle.py:1311–1343). `copy("steering")` runs `_copy_steering`
  (lifecycle.py:1346–1373). `copy_all()` calls all three and returns their
  results as `{"agents": [...], "skills": [...], "steering": [...]}`.
  The existing `_copy_agents`, `_copy_skills`, `_copy_steering` functions in
  `lifecycle.py` become one-line wrappers delegating to `AcademyLoader`.
  Add tests in `tests/unit/test_academy.py`: each `copy(kind)` calls the right
  source directory, unknown kind raises ValueError, `copy_all` calls all three.
  Verify: `pytest tests/unit/ -q` green.

- [x] 4.2  **Update `_finish_crew_setup` and `_reconcile_registry` call sites.**
  In `lifecycle.py`, replace the three separate calls
  `_copy_agents(podman, container, composition_entry)`,
  `_copy_skills(podman, container, composition_entry)`,
  `_copy_steering(podman, container, composition_entry)`
  with `loader = AcademyLoader(podman, container, composition_entry);
  result = loader.copy_all(); copied_agents = result["agents"]`.
  Same replacement in `_reconcile_registry` where `_copy_agents` etc. are called
  on restart (lines ~1848–1868). Verify: `pytest tests/unit/ -q` green.

---

## 5. `LoginFlow` class hierarchy

- [x] 5.1  **Create `transport/login.py` with the abstract base class.**
  Define `LoginFlow(ABC)` with: `backend: ClassVar[str]`,
  `container_prefix: ClassVar[str]`, `image_key: ClassVar[str]`
  (either `"kc_base_image"` for kiro or `"kc_image"` for claude/codex),
  instance state fields (`container`, `exec_id`, `started_at`, `state`,
  `_lock: threading.Lock`). Implement the shared `initiate(podman) -> dict`
  method that runs the six-phase state machine, calling abstract hooks
  `_binary_name()`, `_login_cmd()`, `_prompt_patterns()`, `_url_patterns()`,
  `_code_pattern()`, `_start_container(podman)`, `_nuke_container(podman)`.
  Implement `abort(podman) -> bool` — shared: lock, clear state, nuke container.
  Implement `is_expired() -> bool` using the `_ttl_secs()` abstract method.
  Implement `start_container(podman) -> str` — shared container create/start
  logic; subclass overrides `_container_create_payload(name)` for image/network.
  Define abstract methods: `_binary_name`, `_login_cmd`, `_prompt_patterns`,
  `_url_patterns`, `_code_pattern`, `_ttl_secs`, `auth_exists`, `write_auth`,
  `inject_auth`, `poll(podman)`.
  No tests yet (subclasses tested in 5.2).

- [x] 5.2  **Implement `KiroLoginFlow`, `ClaudeLoginFlow`, `CodexLoginFlow`.**
  `KiroLoginFlow`: backend="kiro", container_prefix=GA_LOGIN_CONTAINER_PREFIX,
  image=kc_base_image, binary="kiro-cli", cmd=["kiro-cli","login","--use-device-flow"],
  prompt_patterns and url_patterns from `_initiate_login` (lifecycle.py:2861–2890),
  `_ttl_secs()=KIRO_LOGIN_TTL_SECS`, `auth_exists=_read_auth_file() != ""`,
  `write_auth` delegates to `_write_auth_file`, `inject_auth` delegates to
  `_inject_auth`, `poll` delegates to `_read_auth_from_crew`.
  `ClaudeLoginFlow`: backend="claude", prefix=GA_CLAUDE_LOGIN_CONTAINER_PREFIX,
  image=kc_image, binary="claude", cmd=["claude","auth","login"], add
  `submit_code(code) -> dict` method (writes to PTY),
  `_is_code_expired() -> bool`, `poll` delegates to `_poll_claude_login_container`.
  `CodexLoginFlow`: backend="codex", prefix=GA_CODEX_LOGIN_CONTAINER_PREFIX,
  image=kc_image, binary="codex-acp", cmd=["codex-acp","login"], `poll`
  delegates to `_poll_codex_login_container`.
  Create module-level singletons: `KIRO_FLOW = KiroLoginFlow()`,
  `CLAUDE_FLOW = ClaudeLoginFlow()`, `CODEX_FLOW = CodexLoginFlow()`,
  `ALL_FLOWS: list[LoginFlow] = [KIRO_FLOW, CLAUDE_FLOW, CODEX_FLOW]`.
  Add `tests/unit/test_login_flows.py`: test initiate/abort/poll for each backend
  using mocked podman; test `is_expired`; test that `ALL_FLOWS` sweeping
  (`flow.abort(podman) if flow.is_expired()`) hits all three.
  Verify: `pytest tests/unit/ -q` green.

- [x] 5.3  **Migrate `lifecycle.py` to delegate to `LoginFlow` singletons.**
  Replace `_initiate_login`, `_initiate_claude_login`, `_initiate_codex_login`,
  `_abort_pending_login`, `_abort_claude_pending_login`, `_abort_codex_pending_login`,
  `_sweep_expired_logins`, `_start_login_container`, `_nuke_login_container`,
  `_start_claude_login_container`, `_nuke_claude_login_container`,
  `_start_codex_login_container`, `_nuke_codex_login_container` with delegating
  wrappers that call the corresponding `LOGIN_FLOW.method(...)`. Keep the
  function names in `lifecycle.py` as one-line wrappers so all existing call
  sites and test patches on `lifecycle.*` continue to resolve.
  Keep `_auth_file_path`, `_read_auth_file`, `_write_auth_file`,
  `_claude_auth_file_path`, `_claude_auth_exists`, `_write_claude_auth_file`,
  `_codex_auth_file_path`, `_codex_auth_exists`, `_write_codex_auth_file` as
  module-level functions (they are also called directly from non-login paths
  like `_finish_crew_setup` and `_logout_post`).
  The three `_*_login_pending` globals in `lifecycle.py` become properties
  forwarding to the flow singletons: `_login_pending = property(lambda: KIRO_FLOW._pending_dict())`.
  Verify: `pytest tests/unit/ -q` green.

- [x] 5.4  **Migrate `server.py` HTTP login handlers to use `LoginFlow` singletons.**
  Replace `_lifecycle._login_pending` attribute reads with `login.KIRO_FLOW.state`
  etc. Replace `_initiate_login(podman)` with `login.KIRO_FLOW.initiate(podman)`.
  Replace `_poll_claude_login_container` call chain with `login.CLAUDE_FLOW.poll(podman)`.
  The route handler bodies become thin: validate auth exists / backend enabled;
  call flow.initiate/poll/abort; return JSON. The module-attribute access
  `_lifecycle._login_pending` is eliminated — replaced by `login.KIRO_FLOW`.
  Verify: `pytest tests/unit/ -q` green.

---

## 6. `CrewLauncher` class

- [x] 6.1  **Create `transport/launcher.py` with `CrewLauncher` skeleton.**
  Define `CrewLauncher(registry: CrewRegistry, podman: PodmanClient, cfg: Config)`.
  Move the per-crew concurrency state dicts from `lifecycle.py` globals into
  `CrewLauncher` instance attributes: `_startup_events`, `_startup_events_lock`,
  `_crew_restart_outcomes`, `_startup_generation`, `_recovery_locks`,
  `_recovery_locks_lock`, `_warm_markers`, `_warm_markers_lock`. Keep
  `_NUKED_DURING_RESTART` as a module-level sentinel (imported from `lifecycle`
  to maintain identity with existing callers).
  Create a module-level singleton `_launcher: CrewLauncher` initialised at the
  bottom of `launcher.py` (after import of the global `registry` singleton and
  `_get_podman()`). Add `get_ensure_running_lock(crew_id)` helper mirroring the
  current `_get_recovery_lock` / `_get_ensure_running_lock` pattern.
  No logic yet — just the skeleton with the concurrency dicts and the singleton.
  No tests yet (next task adds logic). Verify: module imports clean; no test
  regressions from import changes. `pytest tests/unit/ -q` green.

- [x] 6.2  **Implement `CrewLauncher.ensure_running`.**
  Port `lifecycle._ensure_crew_running` (lines 747–1065) as
  `CrewLauncher.ensure_running(self, crew: Crew, crew_id: str, *, touch: bool = True) -> Crew`.
  The concurrency logic (startup events, leader/waiter pattern, generation counter,
  outcome recording) moves from module globals to `self.*` attributes from 6.1.
  The active-limit check and memory gate are extracted to `self._check_active_limit()`
  and `self._check_memory_gate()`. `_ensure_crew_running` in `lifecycle.py` becomes
  a one-line wrapper: `return _launcher.ensure_running(crew, crew_id, touch=touch)`.
  All existing call sites (`_phase1_stale_cookie`, `_phase2_dead_gateway`,
  `_reconcile_registry`, server proxy handlers) continue to call `_ensure_crew_running`
  and get the launcher's implementation via the wrapper.
  Add tests in `tests/unit/test_launcher.py`: concurrent restart serialisation
  (two threads, one becomes waiter, reads leader outcome), active-limit gate,
  memory gate, `_NUKED_DURING_RESTART` sentinel propagation. Tests use mocked
  podman and registry. Verify: `pytest tests/unit/ -q` green.

- [x] 6.3  **Implement `CrewLauncher.finish_setup`.**
  Port `lifecycle._finish_crew_setup` (lines 2168–2408) as
  `CrewLauncher.finish_setup(self, podman, crew_id, container, volume, home_volume,
  auth_b64, composition, composition_entry, *, admiral_secret, dashboard) -> dict`.
  Replace `_copy_agents(...)`, `_copy_skills(...)`, `_copy_steering(...)` with
  `AcademyLoader(podman, container, composition_entry).copy_all()` (task 4.2 is
  a prerequisite). Registry writes use `registry.put(crew)` and `registry.touch(crew_id)`.
  `_finish_crew_setup` in `lifecycle.py` becomes a one-line delegation wrapper.
  Add tests: finish_setup with mocked podman and registry; verify registry.put
  called with correct Crew fields; verify prewarm called at end.
  Verify: `pytest tests/unit/ -q` green.

- [x] 6.4  **Extract `CrewLauncher._run_restart_cycle` and fold into `_reconcile_registry`.**
  The restart logic in `_reconcile_registry` (lifecycle.py:1840–1880) is
  structurally identical to the restart cycle inside `_ensure_crew_running`.
  Extract it as `self._run_restart_cycle(crew: Crew, crew_id: str) -> Crew | None`
  that runs: patch config → stop → start → wait_gateway → mint cookie → update registry.
  `_reconcile_registry` calls `_launcher._run_restart_cycle(crew, cid)` for
  stopped crews on startup. Verify: `pytest tests/unit/ -q` green.

---

## 7. Cleanup and docs

- [x] 7.1  **Audit and remove dead code in `lifecycle.py` and `server.py`.**
  After all wrappers are in place, identify functions in `lifecycle.py` that are
  now empty wrappers with no direct test coverage (only covered via their
  delegating implementation). Mark them for removal. Check that removing each
  wrapper does not break any test. Remove only functions where:
  (a) the wrapper adds zero logic, and (b) no test patches the name directly
  (use `grep -r "_initiate_login\|_ensure_crew_running\|..." tests/` to confirm).
  Target: meaningful line-count reduction in `lifecycle.py`. Do not remove
  anything tested by name. Verify: `pytest tests/unit/ -q` green.

- [x] 7.2  **Update `docs/architecture.md`.**
  Replace the current module-level function descriptions in the transport section
  with a class model diagram and descriptions:
  - `Crew` — data class; `to_dict/from_dict`, `is_idle`, `is_warm`, `gateway_url`
  - `CrewRegistry` — JSON registry with context manager; owns all crew CRUD,
    schedule, batch, and secret operations
  - `LoginFlow` (ABC) / `KiroLoginFlow`, `ClaudeLoginFlow`, `CodexLoginFlow` —
    backend-specific device-flow state machines
  - `AcademyLoader` — parameterised copy of agents/skills/steering into containers
  - `CrewLauncher` — launch state machine; owns concurrency serialisation;
    `ensure_running`, `finish_setup`
  Document the key invariants from design.md (D1 non-reentrant lock, D3 singleton
  launcher, D4 sentinel). Verify: document renders correctly (`cat` check for
  obvious markdown syntax errors).

---

## Workflow follow-up

- Archive the change after review.
