# Design

## Context

`bin/install.sh` is 1633 lines of bash. Its major sections by line range:

| Section | Lines | What it does |
|:--------|:------|:------------|
| Interactive wizard | 57–166 | Backend selection, config/ghostship.yaml generation |
| Defaults + config resolution | 167–395 | Built-in defaults, yaml_config.py invocation, `eval "$_RESOLVED"`, flag parsing |
| Prereqs + Podman machine | 529–791 | python3/podman/podman-compose checks, macOS VM create/start, socket resolution |
| Image builds | 865–1008 | `podman build` for transport, crew, radar images |
| Compose generation | 1065–1230 | bash heredoc → `DATA_DIR/compose.yml` |
| Caddy config generation | 1231–1431 | bash heredoc → `DATA_DIR/caddy/initial-config.json` |
| Transport startup + health | 1432–1541 | `podman-compose up`, health check loop |
| Auth + harness registration | 1542–1633 | `ghostship auth login`, `ghostship setup`, PATH wiring |

The config resolution layer (`eval "$_RESOLVED"`) is already handled by
`bin/lib/yaml_config.py` (Python). The target: every other section follows suit.

See `proposal.md — Why` for motivation.

## Goals / Non-Goals

**Goals:**
- Every substantive section of `install.sh` moved to a Python module under `bin/lib/`
- `install.sh` becomes a ~50-line glue script: shebang, PATH bootstrap, Python check, `exec python3 bin/lib/install.py "$@"`
- Compose and Caddy config generation are unit-testable Python (no bash heredocs)
- `eval "$_RESOLVED"` injection surface eliminated — config flows through Python entirely
- Identical CLI flags, env vars, config keys, and install outcomes (no user-visible change)
- Each module independently importable and testable

**Non-Goals:**
- Changing what install.sh does (same flow, same outputs)
- Rewriting `bin/lib/yaml_config.py` (already Python, already works)
- Moving image builds (podman build invocations) — these stay as subprocess calls from Python
- Changing the `ghostship` CLI entrypoint (`bin/ghostship`)

## Decisions

### D1 — Single top-level `bin/lib/install.py` orchestrator, not scattered `__main__` blocks

Each module (`compose.py`, `caddy.py`, etc.) exposes a Python function, not a
CLI entry point. `bin/lib/install.py` imports them all and orchestrates the
install sequence. `install.sh` calls exactly one command:
`exec python3 bin/lib/install.py "$@"`.

Alternative: each module has its own `__main__` and `install.sh` calls them
sequentially. Rejected — this keeps bash as the control flow layer and
doesn't reduce complexity; the subprocess boundary makes error handling harder.

### D2 — Config passed as a dataclass, not re-read from env vars inside modules

`install.py` resolves all config (via `yaml_config.py`) once into a
`InstallConfig` dataclass (or dict) and passes it to each module as an
argument. Modules are pure functions: `generate_compose(cfg) -> str`.

Alternative: modules read from `os.environ` directly. Rejected — makes modules
harder to test (requires `monkeypatch.setenv`) and couples them to the global
env.

### D3 — compose.yml and initial-config.json generated via explicit dict construction + `yaml`/`json` serialisation

No string templates, no heredocs, no `str.format()`. Build the config as a
Python dict (using existing `bin/lib/vendor/yaml` for compose.yml,
`json.dumps` for Caddy JSON), then serialise. This is what makes the
output testable: a test can assert `cfg["services"]["ga-transport"]["environment"]["PORT"] == "64057"`.

Alternative: `string.Template`. Rejected — still string manipulation; quoting
edge cases remain; output is not inspectable as a dict.

### D4 — Podman subprocess calls stay in `bin/lib/podman.py`, not abstracted further

`podman.py` wraps `subprocess.run(["podman", ...])` directly. No attempt to
create a Podman client class — that's the transport's job (`transport/podman.py`).
Install-time Podman operations (machine create, start, socket probe) are
a thin, explicit list.

### D5 — Wizard prompts stay interactive (stdin/stdout), wizard.py has no GUI

`wizard.py` is a direct port of the bash `_interactive_setup()` function.
Input via `input()`, output via `print()`. No `curses`, no `questionary`.
The only new capability: prompt output goes through a `Prompter` abstraction
(`TerminalPrompter` for real installs, `ScriptedPrompter` for tests) so the
wizard is unit-testable without a real TTY.

## Module boundaries

```
bin/
├── install.sh            ← ~50 lines: shebang + exec python3 bin/lib/install.py "$@"
├── ghostship             ← CLI entrypoint (unchanged)
└── lib/
    ├── yaml_config.py    ← already here (unchanged)
    ├── vendor/           ← PyYAML (unchanged)
    ├── install.py        ← orchestrator: arg parse, config load, calls modules in order
    ├── compose.py        ← generate_compose(cfg: InstallConfig) -> str (YAML)
    ├── caddy.py          ← generate_caddy_config(cfg: InstallConfig) -> str (JSON)
    ├── podman.py         ← ensure_machine(cfg), resolve_socket(cfg) -> str
    └── wizard.py         ← run_wizard(prompter) -> WizardResult
```

`install.py` public interface:
```python
def main(argv: list[str]) -> int: ...
```

`compose.py` public interface:
```python
def generate_compose(cfg: "InstallConfig") -> str: ...   # returns YAML string
```

`caddy.py` public interface:
```python
def generate_caddy_config(cfg: "InstallConfig") -> str:  # returns JSON string
```

`podman.py` public interface:
```python
def check_prerequisites() -> None: ...           # raises on missing tools
def ensure_machine(cfg: "InstallConfig") -> None: ...
def resolve_socket(cfg: "InstallConfig") -> str: ...
```

`wizard.py` public interface:
```python
def run_wizard(prompter: "Prompter") -> "WizardResult": ...
```

## Risks / Trade-offs

- **Subprocess exit codes in Python** — bash `set -e` stops on any failure.
  Python requires explicit `check=True` on every `subprocess.run()` call.
  Risk: a subprocess call that forgets `check=True` silently swallows failures.
  Mitigation: lint rule (`subprocess.run` without `check=` is a warning); all
  subprocess calls in `podman.py` use a thin `run()` helper that always sets
  `check=True` unless explicitly overridden.

- **`eval "$_RESOLVED"` removal** — the existing bash path evals shell-quoted
  KEY=value lines from `yaml_config.py` into the env. The Python replacement
  must reproduce the same env var set exactly (same names, same values) before
  passing `InstallConfig` to modules. Mitigation: integration test asserts
  the same set of env vars are resolved from the same input config.

- **macOS / Linux Podman branching** — `podman.py` inherits the same
  OS-detection logic from bash. The code is simpler in Python (`sys.platform`,
  `shutil.which`) but the branching is still complex. Risk: a regression on
  one platform. Mitigation: unit tests for each branch using mocked
  `subprocess` and `sys.platform`.

## Migration Plan

1. Write modules in order: `compose.py` → `caddy.py` → `podman.py` → `wizard.py` → `install.py`
2. At each step, verify the module produces identical output to the bash section it replaces (diff-based integration test against a known-good config)
3. On the final step, replace `install.sh` body with the glue entry point
4. Rollback: `git revert` — the old `install.sh` is in history; no data migration needed

## Open Questions

None — the approach, module boundaries, and interfaces are fully specified.
