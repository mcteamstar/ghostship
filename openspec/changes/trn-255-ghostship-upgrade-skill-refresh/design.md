# Design

## Context

`ghostship upgrade` is a thin shim (`cmd_upgrade` in `ghostship`) that calls `_exec_script("scripts/install.sh", args)` and exits. `ghostship setup` / `ghostship init` is a separate shim calling `_exec_script("scripts/setup.py", args)`. The two are currently independent; `upgrade` has no awareness of skills.

`scripts/setup.py` is already idempotent — it creates symlinks only if missing or stale, and upserts MCP config entries. Re-running it after an upgrade is safe and fast.

The wizard's post-transport harness-registration block (lines ~1509–1516 of `scripts/install.sh`) currently puts a `_prompt` gate in front of `ghostship setup`, making it opt-in. This is the only change needed there.

## Goals / Non-Goals

**Goals**: Minimal-touch extension — no new modules, no new deps, no transport changes.

**Non-Goals**: Detecting whether skills are already up to date and skipping the refresh; making `--skills` the default for `upgrade` in this release (deferred to a later release after operator feedback).

## Decisions

**D1: `ghostship upgrade --skills` calls `cmd_setup` in-process rather than subprocess.**

`_exec_script` replaces the current process via `execvp`, so there is no "after" for a second step. Instead, `cmd_upgrade` with `--skills` will:
1. Run `scripts/install.sh` via subprocess (`subprocess.run`), capturing exit code.
2. On success (exit 0), call `cmd_setup([])` directly in-process.
3. Forward the combined exit code.

This is the only case where `cmd_upgrade` does not use `_exec_script`. The install output still streams to the terminal because `subprocess.run` inherits stdio.

Alternative considered: two `_exec_script` calls — not possible since `_exec_script` is `execvp` (replaces process). Wrapping in a shell was rejected as adding unnecessary indirection.

**D2: `ghostship skills` is a direct alias — `cmd_skills = cmd_setup` in the dispatch table.**

No new function needed. One line in the dispatch table. `--help` text is slightly different ("refresh skill symlinks, equivalent to `ghostship setup`") so a thin wrapper with its own help string is warranted.

**D3: Wizard setup step made unconditional — remove the `_prompt` gate.**

The wizard is already an interactive flow the operator opted into. Silently not wiring harnesses on a fresh install is a footgun. Remove the prompt; always call `ghostship setup` after the health check passes. Non-fatal on failure (warning + exit 0).

## Risks / Trade-offs

- **[Risk] `ghostship upgrade --skills` runs setup against all detected clients, which may update MCP entries the operator has customised** → Mitigation: `setup.py` upserts by key, preserving other settings; operators who want finer control can run `ghostship setup --agent <target>` directly.
- **[Risk] Wizard calling `ghostship setup` unconditionally may fail in headless/CI deploys where no agent client is installed** → Mitigation: `setup.py` already exits 0 with "no supported agent found" when nothing is detected; failure is non-fatal per the spec.

## Migration Plan

Pure additive change. No config changes, no transport API changes, no data migration. Deploy by running `ghostship upgrade` after merging to `release/0.8.0`.

## Open Questions

None.
