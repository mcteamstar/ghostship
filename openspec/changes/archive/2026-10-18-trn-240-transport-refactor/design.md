# Design

## Context

See proposal.md. OO redesign of the transport layer — no behaviour changes.

## Measured current state

```
server.py      5128 lines   60+ top-level functions, 1 exception class, 0 domain classes
lifecycle.py   4239 lines   80+ top-level functions, 1 exception class, 0 domain classes
registry.py     352 lines   17 top-level functions (all operate on the same dict)
monitors.py     713 lines    6 top-level functions  (2 daemon loops, bind_lifecycle injection)
config.py       453 lines   1 dataclass (Config) — already OO, leave alone
```

The global state graph:

```
registry.py ─── _registry_lock (threading.Lock)
                _NEVER_FIRE_AT, _load_registry, _save_registry   (used 83×)
                _get_crew, _touch_crew                            (used 12×)
                schedule/batch/secret helpers

lifecycle.py ── _startup_events, _startup_events_lock           (per-crew restart gates)
                _crew_restart_outcomes, _startup_generation      (concurrent-restart state)
                _recovery_locks, _recovery_locks_lock            (per-crew recovery serialiser)
                _warm_markers, _warm_markers_lock               (ACP prewarm markers)
                _task_timestamps, _task_timestamps_lock         (in-memory timestamps)
                _login_pending, _login_pending_lock             (kiro device flow state)
                _claude_login_pending, _claude_login_pending_lock (claude flow state)
                _codex_login_pending, _codex_login_pending_lock  (codex flow state)
                _NUKED_DURING_RESTART sentinel

server.py   ── _ensure_running_locks, _ensure_running_locks_lock (asyncio per-crew locks)
                cfg (module-level Config.from_env() singleton)
```

All these globals are shared across server, lifecycle, monitors, and (via
imports) captain. The modules communicate by importing each other's globals
directly, by module-attribute reads (`_lifecycle._login_pending`), and via
`monitors.bind_lifecycle()` injection.

## Class design

### 1. `Crew` dataclass  (`transport/crew.py`, NEW file)

**What data it owns:**

The crew dict written to `crews.json` at `lifecycle.py:2355` (`_finish_crew_setup`).
All fields currently stored in `reg["crews"][crew_id]`:

```python
@dataclass
class Crew:
    crew_id: str                         # the registry key — always carry it with the data
    container: str                       # "gs-<crew_id>"
    volume: str                          # "gs-vol-<crew_id>"
    home_volume: str                     # "gs-home-<crew_id>"
    port: int = 5476                     # CREW_GATEWAY_PORT — effectively constant
    cookie: str = ""
    internal_cookie: str = ""
    status: str = "stopped"              # "running" | "stopped" | "launching"
    composition: str = "spec-ops"
    acp_backend: str = "kiro"            # "kiro" | "claude" | "codex"
    created_at: str = ""                 # ISO-8601 UTC
    last_used: float = 0.0
    warm_until: float = 0.0              # from _warm_markers (currently not in JSON)
    enrolled_agents: list[str] = field(default_factory=list)
    admiral_secret_id: str = ""
    policy_version: str = ""
    policy_signing_key_id: str = ""
    crew_image_version: str = "unknown"
    schedules: list[dict] = field(default_factory=list)
    batches: list[dict] = field(default_factory=list)

    # ── computed / view methods ──────────────────────────────────────────────
    def gateway_url(self) -> str:
        return f"http://{self.container}:{self.port}"

    def is_idle(self, timeout_secs: int) -> bool:
        """True when last_used is older than timeout_secs."""
        return self.last_used > 0 and (time.time() - self.last_used) > timeout_secs

    def is_warm(self) -> bool:
        """True when a fresh ACP prewarm marker is set."""
        return self.warm_until > time.monotonic()

    def to_dict(self) -> dict:
        """Serialise for crews.json (excludes warm_until — in-memory only)."""
        ...

    @classmethod
    def from_dict(cls, crew_id: str, d: dict) -> "Crew":
        """Deserialise from a crews.json entry. Unknown keys are silently ignored."""
        ...
```

**Functions that map to it (call sites to migrate):**
- All 51 `crew["container"]` / `crew.get("cookie")` accesses in server.py, lifecycle.py, files.py
- `_crew_url(crew)` → `crew.gateway_url()`
- `_crew_cookie(crew)` → `f"mc_token_{crew.port}={crew.cookie}"`
- All `reg["crews"][crew_id]` dict constructions → `Crew.from_dict(crew_id, ...)`

**Obstacles / risks:**
- `files.py` also accesses crew dicts (12 sites); must be migrated in the same step
- The `warm_until` field is currently in `_warm_markers` (in-memory, separate lock);
  moving it into Crew means the registry must not persist it — `to_dict()` must
  exclude it; `from_dict()` must initialise it to 0.0. No behaviour change.
- crew_id is currently stored as the dict KEY, not in the value; `Crew` should
  carry `crew_id` explicitly so it is self-describing when passed around.

**Risk:** Medium. ~51 mechanical substitutions plus files.py. No logic changes.

---

### 2. `CrewRegistry`  (`transport/registry.py`, EXTEND existing file)

**What data it owns:**

The JSON file at `REGISTRY_PATH` plus the threading lock. Replaces all 83
`with _registry_lock: reg = _load_registry(); ...; _save_registry(reg)` blocks.

```python
class CrewRegistry:
    def __init__(self, path: Path): ...

    # Context manager — acquires lock, loads, yields self, saves on clean exit
    def __enter__(self) -> "CrewRegistry": ...
    def __exit__(self, exc_type, exc, tb) -> None: ...

    # Crew CRUD
    def get(self, crew_id: str) -> Crew | None: ...
    def put(self, crew: Crew) -> None: ...       # uses crew.crew_id as key
    def remove(self, crew_id: str) -> None: ...
    def list(self) -> list[Crew]: ...

    # Schedule helpers (currently _upsert_crew_schedule etc.)
    def upsert_schedule(self, crew_id: str, job: dict) -> None: ...
    def remove_schedule(self, crew_id: str, job_id: str) -> None: ...
    def get_schedules(self, crew_id: str) -> list[dict]: ...

    # Batch helpers
    def write_batch(self, crew_id: str, batch_id: str, ...) -> dict | None: ...
    def get_batch(self, crew_id: str, batch_id: str) -> dict | None: ...
    def update_batch_status(self, crew_id: str, batch_id: str, status: str) -> dict | None: ...
    def delete_batch(self, crew_id: str, batch_id: str) -> bool: ...
    def find_batch_by_task_ids(self, crew_id: str, task_ids: list[str]) -> dict | None: ...

    # Secret helpers (crew-specific, currently in _write_crew_secret etc.)
    def write_secret(self, crew_id: str, secret: str) -> None: ...
    def read_secret(self, crew_id: str) -> str | None: ...
    def delete_secret(self, crew_id: str) -> None: ...

    # Touch (last_used update)
    def touch(self, crew_id: str) -> None: ...
```

The existing module-level `_registry_lock`, `_load_registry`, `_save_registry`,
`_get_crew`, `_touch_crew`, and all schedule/batch/secret helpers stay as
**private** implementations called by the class — unchanged code, new public
surface. Existing call sites migrated one group at a time.

**Functions that map to it:**
- All 83 `with _registry_lock:` blocks in server.py (43), lifecycle.py (17),
  monitors.py (13), registry.py (7), captain.py (3)
- `_get_crew` → `registry.get(crew_id)`
- `_touch_crew` → `registry.touch(crew_id)`
- All schedule/batch/secret functions → delegated through registry methods

**Obstacles / risks:**
- `monitors.py` imports `_registry_lock`, `_load_registry`, etc. directly from
  `registry` at module load (NOT via `bind_lifecycle`). After `CrewRegistry` is
  introduced, monitors must still work — easiest approach: keep the module-level
  names as module attributes pointing at the class internals.
- `captain.py` has 3 `with _registry_lock:` uses — must be migrated too.
- The context manager pattern changes `with _registry_lock: reg = _load_registry()...`
  to `with registry: registry.put(...)` — saves the lock+load+save boilerplate.
  Clean exit auto-saves; exception exit does NOT save (data is not corrupted by
  a failed partial update).

**Risk:** High. 83 call sites, 5 files. Do in multiple sub-steps. Each sub-step:
one file's call sites migrated, tests green.

---

### 3. `LoginFlow` ABC + subclasses  (`transport/login.py`, NEW file)

**What data it owns (per-instance):**

Each instance represents one in-flight or completed login flow for one backend.
State fields (currently scattered across three `_*_login_pending` global dicts):

```python
class LoginFlow(ABC):
    backend: ClassVar[str]           # "kiro" | "claude" | "codex"
    container_prefix: ClassVar[str]  # GA_LOGIN_CONTAINER_PREFIX etc.

    # Instance state (mirrors current _*_login_pending dict)
    container: str | None = None
    exec_id: str | None = None
    started_at: float = 0.0
    state: str = "starting"          # "starting" | "started" | "awaiting_code" | "code_submitted"

    # Auth persistence
    @abstractmethod
    def auth_exists(self) -> bool: ...

    @abstractmethod
    def write_auth(self, data: bytes | str) -> None: ...

    @abstractmethod
    def inject_auth(self, podman: PodmanClient, container: str) -> None: ...

    # Flow control (implemented in base class using _run_pty_login_flow)
    @abstractmethod
    def _binary_name(self) -> str: ...

    @abstractmethod
    def _login_cmd(self) -> list[str]: ...

    @abstractmethod
    def _prompt_patterns(self) -> list[tuple]: ...

    @abstractmethod
    def _url_patterns(self) -> list[re.Pattern]: ...

    @abstractmethod
    def _code_pattern(self) -> re.Pattern | None: ...

    # Public API
    def initiate(self, podman: PodmanClient) -> dict:
        """Six-phase flow — shared logic, abstract hooks for backend specifics."""
        ...

    def poll(self, podman: PodmanClient) -> bytes | str | None:
        """Poll for credentials; return raw credential bytes/str or None."""
        ...

    def abort(self, podman: PodmanClient) -> bool: ...

    def is_expired(self) -> bool: ...

    def start_container(self, podman: PodmanClient) -> str: ...

    def nuke_container(self, podman: PodmanClient) -> None: ...
```

**Subclasses:**

```
KiroLoginFlow   — kiro-cli device flow, returns str (b64 JSON auth rows)
                  poll: _read_auth_from_crew()
                  auth: _write_auth_file / _inject_auth
                  extra: _submit_login_code not needed (URL-only flow)

ClaudeLoginFlow — claude auth login PTY flow, returns bytes (tar of ~/.claude/)
                  poll: _poll_claude_login_container()
                  auth: _write_claude_auth_file / _inject_claude_auth
                  extra: submit_code(code) → write to PTY; state="code_submitted"

CodexLoginFlow  — codex-acp login PTY flow, returns bytes (tar of ~/.codex/)
                  poll: _poll_codex_login_container()
                  auth: _write_codex_auth_file / _inject_codex_auth
                  extra: submit_code(code) if present (optional for codex)
```

**Module-level state migration:**

The three global `_*_login_pending` dicts and their locks currently live in
`lifecycle.py` and are read by `server.py` via `_lifecycle.*`. After extraction:
- Each `LoginFlow` subclass is a module-level singleton in `login.py`
- `login.py` exports `KIRO_FLOW`, `CLAUDE_FLOW`, `CODEX_FLOW`
- `server.py` accesses `login.KIRO_FLOW.initiate(podman)` instead of
  `_initiate_login(podman)` and `_lifecycle._login_pending`
- Existing HTTP handlers become thin wrappers over the flow instances

**Obstacles / risks:**
- `_sweep_expired_logins` (lifecycle.py:3195) touches all three backends.
  With singleton flow objects it becomes `for flow in ALL_FLOWS: flow.sweep(podman)`
- server.py currently reads `_lifecycle._login_pending` via module-attribute
  access (not imported value) because the global is reassigned. The singleton
  pattern eliminates the reassignment — `KIRO_FLOW` itself is stable; its
  internal state changes. This removes the need for the `import lifecycle as _lifecycle`
  module-reference workaround.
- Tests that mock `_lifecycle._login_pending` directly will need updating to
  patch `login.KIRO_FLOW` instead. ~20 test files touch login flows; coordinate
  test updates in the same task as the implementation.

**Risk:** Medium-High. The most complex class because of the module-global
mutation pattern and the test surface. Implement last (after Crew and
CrewRegistry are stable).

---

### 4. `AcademyLoader`  (`transport/academy.py`, EXTEND existing file)

**What data it owns:**

A thin stateless wrapper over the four copy operations. No persistent state.

```python
class AcademyLoader:
    KINDS = ("agents", "skills", "steering")  # "policy" handled separately — needs signing key

    def __init__(
        self,
        podman: PodmanClient,
        container: str,
        composition_entry: dict | None = None,
    ) -> None: ...

    def copy(self, kind: str) -> list[str]:
        """Copy one kind ("agents" | "skills" | "steering") and return copied names."""
        ...

    def copy_all(self) -> dict[str, list[str]]:
        """Copy all three standard kinds. Returns {kind: [names]}."""
        ...
```

**Functions that map to it:**
- `_copy_agents(podman, container, composition_entry)` → `AcademyLoader(...).copy("agents")`
- `_copy_skills(podman, container, composition_entry)` → `AcademyLoader(...).copy("skills")`
- `_copy_steering(podman, container, composition_entry)` → `AcademyLoader(...).copy("steering")`

Note: `_inject_policy` is NOT folded in — it has a different signature
(`composition: str, policy_signing_key: str`) and a different execution model
(container exec + signing). It stays as a function.

**Obstacles / risks:**
- `_copy_agents` also writes `mcp.json` — this logic is part of the "agents" copy
  operation and must remain so. The `AcademyLoader.copy("agents")` method inherits it.
- `_finish_crew_setup` and `_reconcile_registry` call these functions. The migration
  is mechanical: replace three separate calls with one `AcademyLoader(...).copy_all()`.

**Risk:** Low. Small, self-contained, easy win.

---

### 5. `CrewLauncher`  (`transport/launcher.py`, NEW file)

**What data it owns:**

The per-launch state machine and its configuration. Depends on `CrewRegistry`
and `PodmanClient` passed in — no global state access.

```python
class CrewLauncher:
    def __init__(
        self,
        registry: "CrewRegistry",
        podman: "PodmanClient",
        cfg: "Config",
    ) -> None: ...

    def ensure_running(self, crew_id: str, *, touch: bool = True) -> "Crew":
        """Public surface: bring crew to ready state — cold launch is done via
        server.launch(), not here. ensure_running handles:
        - already-running + alive gateway → return immediately (fast path)
        - already-running + dead gateway → stop + restart cycle
        - stopped → restart cycle (requires prior registry entry)
        Returns updated Crew or _NUKED_DURING_RESTART sentinel.
        """
        ...

    def finish_setup(self, crew_id: str, container: str, volume: str,
                     home_volume: str, auth_b64: str, composition: str,
                     composition_entry: dict | None, *, admiral_secret: str,
                     dashboard: bool = False) -> dict:
        """Full post-auth setup: copy agents/skills/steering, patch config,
        restart, mint cookie, write registry entry. Called by server.launch()
        after the crew container is created and auth is confirmed."""
        ...

    # ── Private phase methods ─────────────────────────────────────────────────
    def _check_active_limit(self) -> None: ...     # raises RuntimeError if at limit
    def _check_memory_gate(self) -> None: ...      # raises RuntimeError if insufficient RAM
    def _run_restart_cycle(self, crew: Crew) -> Crew: ...  # stop/patch/start/wait/cookie
    def _phase0_transient_503(self, ...) -> Any: ...
    def _phase1_stale_cookie(self, ...) -> Any: ...
    def _phase2_dead_gateway(self, ...) -> Any: ...
```

**Functions that map to it:**

| Current function | Maps to |
|---|---|
| `lifecycle._ensure_crew_running` (747–1065) | `CrewLauncher.ensure_running` |
| `lifecycle._finish_crew_setup` (2168–2408) | `CrewLauncher.finish_setup` |
| Active-limit check inside `_ensure_crew_running` | `_check_active_limit` |
| Memory gate inside `_ensure_crew_running` | `_check_memory_gate` |
| `lifecycle._phase0_transient_503` | `CrewLauncher._phase0_transient_503` |
| `lifecycle._phase1_stale_cookie` | `CrewLauncher._phase1_stale_cookie` |
| `lifecycle._phase2_dead_gateway` | `CrewLauncher._phase2_dead_gateway` |
| Restart logic in `_reconcile_registry` | `CrewLauncher._run_restart_cycle` |

**Obstacles / risks:**
- `_ensure_crew_running` uses `_startup_events`, `_startup_events_lock`,
  `_crew_restart_outcomes`, `_startup_generation` (all per-crew global dicts in
  lifecycle.py). These serialise concurrent restart attempts. `CrewLauncher` must
  own these dicts internally (keyed by crew_id) so concurrent callers use the
  same launcher instance. This means `CrewLauncher` must be a singleton (or
  module-level instance) — not constructed fresh per call. The approach: one
  module-level `_launcher` instance in `launcher.py`, injected into server and
  lifecycle.
- `_crew_api_with_recovery` is currently a standalone function (lifecycle.py:653)
  that holds `_get_recovery_lock(crew_id)`. If the phase functions are methods on
  `CrewLauncher`, `_crew_api_with_recovery` should also become a method. However,
  `_crew_api_with_recovery` is called from many places (monitors, server, lifecycle)
  that are NOT the launcher. Safest approach: `_crew_api_with_recovery` stays as
  a standalone function; the launcher's phase methods are factored out but called
  from the existing function (keeping the recovery lock logic intact).
- `_finish_crew_setup` calls `_prewarm_crew` at the end — `CrewLauncher.finish_setup`
  must do the same. `_prewarm_crew` depends on `_crew_api_with_recovery` which
  depends on the recovery lock; this is fine if recovery stays as standalone.
- The **NON-REENTRANT CONTRACT** (D1 in lifecycle.py:653–718): `_crew_api_with_recovery`
  holds `_get_recovery_lock(crew_id)` and the phase methods call `_ensure_crew_running`
  (now `launcher.ensure_running`). The non-re-entrancy must be preserved — the
  launcher's ensure_running must NOT internally call crew_api_with_recovery for
  the same crew (it uses `_crew_api` directly). Document this explicitly.

**Risk:** High. Largest and most interdependent. Must be done LAST, after Crew,
CrewRegistry, AcademyLoader, and LoginFlow are stable.

---

## Duplication catalogue (grounded in code)

### A. Registry read-modify-write (83 occurrences, 5 files)
Pattern: `with _registry_lock: reg = _load_registry(); reg["crews"][...] = ...; _save_registry(reg)`
→ Eliminated by `CrewRegistry` context manager.

### B. 0600 atomic file write (7 occurrences, 4 files)
Pattern: `fd = os.open(..., O_WRONLY|O_CREAT|O_TRUNC, 0o600); f = os.fdopen(fd); f.write(...); os.fsync(...)`
Appears in: `_write_auth_file`, `_write_claude_auth_file`, `_write_codex_auth_file`,
`_save_registry`, `_write_crew_secret`, registry.py, files.py.
→ Extract `_write_secret_file(path, data)` utility; fold all seven sites into it.
Belongs in `registry.py` (used there most) or a new `transport/atomicfile.py`.

### C. Login flow state machine (3 backends × 6 phases)
`_initiate_login` / `_initiate_claude_login` / `_initiate_codex_login` —
each ~150 lines. Structurally identical phases, different binary names, URL
patterns, prompt patterns, auth-injection methods.
→ Eliminated by `LoginFlow` base class.

### D. Login container lifecycle (3 × 2 = 6 functions)
`_start_login_container` / `_nuke_login_container` ×3 backends — each 15–30 lines.
Container name prefix, image choice, and the nuke prefix-check vary; the
create/start and stop/remove patterns are identical.
→ Folded into `LoginFlow.start_container()` / `LoginFlow.nuke_container()`.

### E. Auth file helpers (3 × 3 = 9 functions)
`_auth_file_path` / `_*_auth_exists` / `_write_*_auth_file` × 3 backends.
→ Folded into `LoginFlow.auth_path()` / `LoginFlow.auth_exists()` / `LoginFlow.write_auth()`.

### F. Academy copy operations (3 functions ~identical bodies)
`_copy_agents`, `_copy_skills`, `_copy_steering` — all: `src=Path(/kind); manifest = _load_crew_manifest(composition_entry); selection = manifest[kind]; for item in src.glob/iterdir: if _manifest_selects(...): tar and archive_put`
→ Eliminated by `AcademyLoader.copy(kind)`.

---

## Migration strategy and dependency order

```
Step 1: Crew dataclass      — purely additive; no logic change
Step 2: CrewRegistry        — replaces 83 lock+load+save blocks
Step 3: AcademyLoader       — small; replaces 3 copy functions
Step 4: LoginFlow hierarchy — replaces 3 login state machines
Step 5: CrewLauncher        — consolidates _ensure_crew_running + _finish_crew_setup
Step 6: Cleanup + docs
```

Each step: introduce class, migrate call sites, `pytest tests/unit/ -q` green, commit.
Never break tests mid-step.

## Invariants

- All MCP tool signatures unchanged
- All REST endpoint paths and response shapes unchanged
- `pytest tests/unit/ -q` green after every commit
- No new environment variables or config keys
- No changes to `crews.json` serialisation format (to_dict/from_dict preserve it)
- `monitors.py` `bind_lifecycle` injection pattern preserved until CrewLauncher lands

## Design notes (key decisions)

**D1 (non-reentrant recovery lock):** `_crew_api_with_recovery` holds
`_get_recovery_lock(crew_id)` for the entire call including any phase's call
into `ensure_running`. Code called UNDER this lock must use `_crew_api` directly,
never `_crew_api_with_recovery`. This invariant is preserved through all steps.

**D2 (warm_until in-memory only):** The `warm_until` field on `Crew` is NOT
serialised to JSON — it is initialised to 0.0 on `from_dict`. The in-memory
`_warm_markers` dict is drained into `Crew.warm_until` at load time and
updated when the crew object is mutated.

**D3 (singleton launcher):** `CrewLauncher` owns the per-crew restart
concurrency state (`_startup_events`, etc.). A single module-level instance
is created in `launcher.py` and shared by all callers. Constructing a new
launcher per call would lose the concurrency serialisation.

**D4 (_NUKED_DURING_RESTART sentinel):** This sentinel is returned (not raised)
by `ensure_running` when a concurrent `nuke()` removes the crew during restart.
It must remain a sentinel identity check (`is _NUKED_DURING_RESTART`), not a
typed exception, to preserve the existing behaviour at all call sites.
