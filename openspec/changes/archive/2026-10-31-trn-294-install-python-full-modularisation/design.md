# Design

## Context

See `proposal.md — Why` for motivation.

`bin/install.sh` is ~1633 lines of bash. The structural problem is layered:

1. `eval "$_RESOLVED"` ingests yaml_config.py output as shell code — an injection
   surface flagged by the indy-0.10.0 security review (H-2).
2. Four sections — compose.yml heredoc, Caddy JSON heredoc, Podman provisioning,
   and the wizard flow — are bash that cannot be unit-tested without running Podman
   or provisioning a machine.
3. Two helper libraries (`agent_backends.sh`, `portal_host.sh`) duplicate logic
   already in Python (`yaml_config.py`, `transport/config.py`); a Python parity
   test exists but the canonical implementation remains in shell.

TRN-287 proposed this decomposition but produced no implementation. This change
executes it in full.

Current state of `bin/lib/`:
```
bin/lib/
├── yaml_config.py       ← already Python (config parsing, is-loopback)
├── vendor/yaml/         ← vendored PyYAML (no pip, no network)
├── agent_backends.sh    ← shell (normalise, validate, check_default)
└── portal_host.sh       ← shell (API-key resolution, exposure check)
```

Target state after this change:
```
bin/lib/
├── yaml_config.py       ← unchanged
├── vendor/yaml/         ← unchanged
├── compose.py           ← NEW: compose.yml generation
├── caddy.py             ← NEW: Caddy initial-config.json generation
├── podman_setup.py      ← NEW: Podman machine/instance provisioning
├── wizard.py            ← NEW: interactive terminal I/O
├── agent_backends.py    ← NEW: Python port of agent_backends.sh
├── portal_host.py       ← NEW: Python port of portal_host.sh
├── agent_backends.sh    ← DEPRECATED: one-line delegator to .py (kept for sourced callers)
└── portal_host.sh       ← DEPRECATED: one-line delegator to .py (kept for sourced callers)
```

`install.sh` shrinks to: arg parsing → `yaml_config.py resolve` (via import,
not eval) → `podman_setup.py` → image builds → `compose.py` → `caddy.py` →
compose up → health probe → optional `wizard.py`.

## Goals / Non-Goals

**Goals:**
- Eliminate every `eval "$_RESOLVED"` in `install.sh`, `start.sh`, and
  `uninstall.sh`.
- Each new `bin/lib/*.py` module is importable and unit-testable in isolation
  (no subprocess, no live Podman).
- `install.sh` final length ≤100 lines (excluding blank/comment).
- `start.sh` and `uninstall.sh` also updated to remove their `eval "$_RESOLVED"`
  patterns (both source `portal_host.sh`; both call yaml_config.py via subprocess).
- Parity tests pass: Python modules produce identical output to the shell they replace.

**Non-Goals:**
- Rewriting `transport/` (already Python, already modular).
- Changing any user-visible flag or configuration key.
- Introducing new Python dependencies beyond the vendored PyYAML.
- Removing `agent_backends.sh` / `portal_host.sh` entirely (tests source them;
  deprecation only in this change).

## Decisions

### D1 — eval elimination strategy: replace subprocess-emit-eval with direct import

**Decision:** `yaml_config.py` currently emits `KEY=value` lines that `install.sh`
`eval`s. Replace with: install.sh calls `python3 bin/lib/install_main.py` as the
new entry point; `install_main.py` imports `yaml_config` directly and passes the
resolved config dict to each sub-module. `install.sh` becomes a short bash shim
that validates prerequisites (Podman available, python3 available) then
`exec python3 bin/lib/install_main.py "$@"`.

**Alternative considered:** Keep shell as primary and call each Python module
via subprocess with `--output-env` for shell-safe key=value. Rejected: still
requires some form of eval to get values back into the shell environment, just
wrapped differently.

**Why exec-to-Python wins:** Single process boundary; no string escaping path;
all modules communicate via Python objects; the eval surface is gone entirely.

### D2 — compose.yml generation: dataclass + PyYAML dump

**Decision:** `compose.py` builds the compose document as a Python dict (using
a `ComposeConfig` dataclass for required fields) and serialises with
`yaml.dump(default_flow_style=False)`. Conditional sections (secrets, optional
bind mounts, TLS env vars) are constructed in Python logic before the dump.

**Alternative considered:** `string.Template` interpolation (as TRN-287 suggested).
Rejected: still string-based; quoting edge cases remain; no structural validation.

**Why dataclass+dump wins:** YAML structure is guaranteed correct; no quoting
edge cases; each conditional is a Python `if`, testable in isolation.

### D3 — Caddy config: build dict, json.dumps

**Decision:** `caddy.py` builds `initial-config.json` as a Python dict and
serialises with `json.dumps(indent=2)`. Auth routes are constructed as Python
list comprehensions over the known route templates.

**No vendored dependency:** `json` is stdlib; no new imports needed.

### D4 — Podman provisioning: subprocess calls, no eval

**Decision:** `podman_setup.py` calls `subprocess.run(["podman", ...], check=True)`
for all Podman operations. Socket path is resolved via `subprocess.run` output
(captured as a string, not eval'd into the shell environment). On Linux with a
dedicated instance the `systemd.service` unit file is written via Python file I/O.

**Subprocess not eval:** The socket path from `podman machine inspect` or
`id -u` is captured as a Python string and returned from the function, never
injected back into a shell.

### D5 — Wizard: `wizard.py` owns all interactive terminal I/O

**Decision:** `wizard.py` wraps `input()` and `print()` calls with the same
`_prompt` / `_interactive_setup` logic, plus the post-install auth offers.
It receives a config dict and returns the operator's choices as a Python dict.

**Testability:** Caller can inject a fake `input` callable (dependency-injected
via parameter) for unit tests without patching builtins.

### D6 — Shell callers (start.sh, uninstall.sh): migrate to Python submodule calls

**Decision:** `start.sh` and `uninstall.sh` still need config resolution and
some portal-host logic. They are updated to call `python3 bin/lib/start_ops.py`
and `python3 bin/lib/uninstall_ops.py` respectively — thin Python wrappers that
import yaml_config directly and perform the platform-specific operations. The
`eval "$_RESOLVED"` lines in both are removed.

**Alternative:** Keep start.sh/uninstall.sh as-is and only fix install.sh.
Rejected: the eval surface and the duplicate portal_host sourcing remain; the
spec requirement for eval elimination covers all three scripts.

### D7 — agent_backends.sh / portal_host.sh: keep as deprecated one-liners

**Decision:** Both shell files are retained as one-liner delegators:
```bash
python3 "$(dirname "${BASH_SOURCE[0]}")/agent_backends.py" "$@"
```
They continue to `source`-able for callers that today source them directly
(e.g. `tests/unit/test_install.py` static checks). Their internal functions
are no longer defined in shell; callers that use the function API need to be
updated to call the Python module directly. A grep for `agent_backends_normalise`
and `portal_resolve_api_key` in test files will identify all such call sites.

## Risks / Trade-offs

- [Risk] Tests that source `agent_backends.sh` or `portal_host.sh` and call
  their bash functions directly will break. → Mitigation: grep all test and
  script files for the function names before removing shell function bodies;
  update each call site to use the Python module.

- [Risk] `exec`-ing into Python from install.sh means the rest of install.sh
  (after the exec) is unreachable. → Mitigation: all install logic lives in
  `install_main.py`; the bash shim is only arg-forwarding and prereq checks,
  so there is no "rest of install.sh" to worry about.

- [Risk] PyYAML dump ordering may differ from the manual heredoc ordering.
  → Mitigation: use `sort_keys=False` in yaml.dump; add a canonical output
  test to `test_compose.py` that asserts service order.

- [Risk] `python3` may not be on PATH at the point `install.sh` execs into it.
  → Mitigation: the existing `command -v python3` guard runs before the exec;
  the error message is unchanged.

## Migration Plan

1. Add `bin/lib/compose.py` + `tests/unit/test_compose.py`; remove heredoc
   from `install.sh`; verify CI passes.
2. Add `bin/lib/caddy.py` + `tests/unit/test_caddy.py`; remove Caddy block
   from `install.sh`; verify CI passes.
3. Add `bin/lib/agent_backends.py` + `bin/lib/portal_host.py`; update shell
   callers; deprecate `.sh` files; verify parity tests pass.
4. Add `bin/lib/podman_setup.py`; remove Podman provisioning from `install.sh`;
   verify CI passes.
5. Add `bin/lib/wizard.py`; remove `_interactive_setup` from `install.sh`;
   verify CI passes.
6. Introduce `bin/lib/install_main.py` that imports all modules; shrink
   `install.sh` to prereq-check + `exec python3 bin/lib/install_main.py "$@"`.
7. Update `start.sh` and `uninstall.sh` to remove their `eval "$_RESOLVED"`
   lines and portal_host sourcing; replace with Python sub-module calls.
8. Run full test suite; assert `install.sh` line count ≤100.
9. Run `openspec validate --change trn-294-install-python-full-modularisation`.

Rollback: each phase is an independent commit. Reverting any phase restores the
removed bash section. No data-format change is involved.

## Open Questions

None. All design decisions are resolved and the task breakdown below is
unambiguous.
