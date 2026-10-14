# Design

## Context

See proposal.md. OO redesign of the transport layer — no behaviour changes.

## Current state (measured)

```
server.py    5128 lines  ~60 top-level functions, no classes
lifecycle.py 4239 lines  ~80 top-level functions, no classes
```

The entire domain state is one global `dict` (`_registry`) protected by a threading lock, accessed directly by functions throughout both files.

## Class design

### `Crew` (replaces raw `dict`)

```python
@dataclass
class Crew:
    crew_id: str
    container_id: str
    volume: str
    home_volume: str
    composition: str
    acp_backend: str
    gateway_url: str
    dashboard_port: int | None = None
    warm_until: float = 0.0
    last_task_at: float | None = None
    dashboard_session_id: str | None = None
    # ... remaining fields

    def is_idle(self, timeout_secs: int) -> bool: ...
    def is_warm(self) -> bool: ...
    def to_dict(self) -> dict: ...

    @classmethod
    def from_dict(cls, data: dict) -> "Crew": ...
```

Eliminates `crew.get("container_id", "")` scattered across ~150 call sites. Serialisation to/from the JSON registry file uses `to_dict()` / `from_dict()`.

### `CrewRegistry` (replaces global `_registry` dict + lock)

```python
class CrewRegistry:
    def __init__(self, path: Path): ...
    def get(self, crew_id: str) -> Crew | None: ...
    def put(self, crew_id: str, crew: Crew) -> None: ...
    def remove(self, crew_id: str) -> None: ...
    def list(self) -> list[tuple[str, Crew]]: ...
    def load(self) -> None: ...       # reads JSON from disk
    def save(self) -> None: ...       # writes JSON to disk
    def __enter__(self) -> "CrewRegistry": ...  # context manager for atomic read-modify-write
    def __exit__(self, *_): ...
```

The repeated pattern:
```python
with _registry_lock:
    reg = _load_registry()
    reg["crews"][crew_id] = ...
    _save_registry(reg)
```
becomes:
```python
with registry:
    registry.put(crew_id, crew)
```

### `CrewLauncher` (replaces `_ensure_crew_running` + `_finish_crew_setup` + phases)

```python
class CrewLauncher:
    def __init__(self, registry: CrewRegistry, podman: PodmanClient, cfg: Config): ...

    def ensure_running(self, crew_id: str) -> Crew:
        """Bring a crew to ready state — cold launch, warm resume, or recovery."""
        ...

    def _cold_launch(self, crew_id: str, ...) -> Crew: ...
    def _warm_resume(self, crew: Crew) -> Crew: ...
    def _recover_phase0(self, crew: Crew) -> Crew: ...   # transient 503
    def _recover_phase1(self, crew: Crew) -> Crew: ...   # stale cookie
    def _recover_phase2(self, crew: Crew) -> Crew: ...   # dead gateway
    def _finish_setup(self, crew: Crew) -> Crew: ...
```

The current `_ensure_crew_running` is ~330 lines with the phases scattered across `lifecycle.py`. `CrewLauncher.ensure_running` makes the state machine visible in one place.

### `LoginFlow` base + subclasses (replaces three parallel login function sets)

```python
class LoginFlow(ABC):
    backend: str

    @abstractmethod
    def initiate(self, podman: PodmanClient) -> dict: ...

    @abstractmethod
    def poll(self) -> dict: ...

    def logout(self, podman: PodmanClient) -> None:
        # shared cleanup logic
        ...

class KiroLoginFlow(LoginFlow):
    backend = "kiro"
    def initiate(self, podman): ...
    def poll(self): ...

class ClaudeLoginFlow(LoginFlow):
    backend = "claude"
    def initiate(self, podman): ...
    def poll(self): ...
    def exchange_code(self, code: str) -> dict: ...  # claude-specific

class CodexLoginFlow(LoginFlow):
    backend = "codex"
    def initiate(self, podman): ...
    def poll(self): ...
```

### `AcademyLoader` (replaces four identical copy functions)

```python
class AcademyLoader:
    KINDS = ("agents", "skills", "steering", "policies", "orders", "mcp")

    def __init__(self, podman: PodmanClient, container: str,
                 composition_entry: dict | None = None): ...

    def copy(self, kind: str) -> list[str]: ...
    def copy_all(self) -> dict[str, list[str]]: ...
```

## Migration strategy

Each step: introduce class, migrate call sites, run `pytest tests/unit/ -q`, commit. Never break tests mid-step.

1. `Crew` dataclass — purely additive, `from_dict`/`to_dict` makes it drop-in
2. `CrewRegistry` — replace global dict + lock; update all call sites
3. `AcademyLoader` — small, isolated, easy win
4. `LoginFlow` hierarchy — extract from server.py, test each backend
5. `CrewLauncher` — largest, do last; requires Crew and CrewRegistry to be in place first

## Invariants

- All MCP tool signatures unchanged
- All REST endpoint paths and response shapes unchanged
- `pytest tests/unit/ -q` green after every commit
- No new environment variables or config keys
