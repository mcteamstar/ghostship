## Context

See `proposal.md` - Why. The mechanical root cause: `install.sh` sources `--config <path>` early (before flag parsing), then resolves most variables with `VAR="${VAR:-default}"` executed *after* that sourcing. Bash's `${VAR:-default}` only applies `default` when `VAR` is unset or empty — it can't distinguish "empty because nothing set it" from "already holds a value inherited from the calling shell's exported environment." `PORT=64057` (a plain literal assignment at `install.sh:47`, *before* config sourcing) is the one variable that doesn't have this problem, purely as a side effect of where it happens to sit in the file, not a deliberate pattern applied elsewhere.

`uninstall.sh` picked up the same shape when `--config`/`GA_MACHINE_NAME` support was added to it earlier on this branch (`_MACHINE_NAME="${GA_MACHINE_NAME:-ghost-academy}"`, sourced-config-then-fallback, same leak).

Separately, `install.sh:475-498` bakes the script's own already-resolved shell variables into the transport container's `-e "VAR=..."` flags. Those lines also use `${VAR:-default}` — but by that point in execution `$VAR` is the script's own local variable (already correctly resolved via config file/flag), not a fresh read of the host's environment, so they are unaffected by this change and stay exactly as they are.

## Goals / Non-Goals

**Goals:**
- Every config variable in `install.sh` and `uninstall.sh` resolves as: literal built-in default → `--config` file → CLI flag (where one exists), with no ambient-environment-variable tier at any point.
- The live `installation` and `config-file` specs, `docs/configuration.md`, and the other install docs accurately describe this resolution order and the corrected `ghost-academy` default.
- Test coverage proves an ambient env var is ignored, not just that config/flag values are honored.

**Non-Goals:**
- Changing which variables get a CLI flag. No new flags are added by this change (see proposal.md's composite-flag note re: `--public-url`).
- Touching the transport container's own runtime environment mechanism (`-e` flags at `podman run`, or anything `transport/server.py` reads from `os.environ`). That is standard container configuration and stays as-is.
- Migrating `GA_FILE_PUBLIC_URL`/`GA_MCP_PUBLIC_URL` further toward `GA_HOST_URL` — that migration is already tracked separately and is untouched here.

## Decisions

**Move every default assignment to before config-file sourcing, matching `PORT`'s existing shape.** Alternative considered: explicitly `unset VAR` for every supported name before sourcing, then apply `${VAR:-default}` afterward as today. Rejected — it's the same outcome with an extra step and an easy-to-miss maintenance hazard (a newly-added variable that isn't added to the `unset` list silently reintroduces the leak). A literal `VAR=default` line before sourcing is self-contained per-variable and matches the one pattern in the file that was already correct.

**Do not touch the `-e "VAR=${VAR:-default}"` lines in the transport `run` command.** These aren't reading ambient env (see Context) — they're a redundant defensive default for variables that otherwise get no explicit default earlier in the script (e.g. `GA_MAX_CREWS`, `GA_IDLE_TIMEOUT_SECS`). Leaving them alone avoids conflating two different concerns (host-shell config resolution vs. container env construction) in one diff.

**`uninstall.sh` gets the identical fix, not a divergent one.** It already gained `--config` support and a `GA_MACHINE_NAME` default this branch; that default assignment moves before its own config-sourcing block, same as `install.sh`.

**Docs restructure states the three-tier order once, prominently, near the top of `docs/configuration.md`**, rather than leaving it implied by a per-variable table. The existing "Supported variables" table (flag-mapped vars only) stays, but gets a sentence clarifying that the rest of the variable table above it is config-file-only — no flag, and (after this change) no ambient env either.

## Risks / Trade-offs

- **[Risk]** Someone currently relies on exporting a variable (e.g. in a wrapper script or CI job) instead of using `--config` or a flag → their install silently reverts to defaults post-change, with no error. **Mitigation**: this was never a documented or spec'd input (confirmed: the current `config-file` spec's resolution order already only names config file → flags → defaults, omitting env entirely) — flagging it in the proposal as **BREAKING** is the most we owe, since there's no prior contract to deprecate. `docs/configuration.md`'s uplift should call this out as a callout box for anyone upgrading.
- **[Risk]** Missing one of the ~20 variables when moving default assignments could leave a partial leak. **Mitigation**: `tasks.md` enumerates every variable currently read by `install.sh`/`uninstall.sh` individually rather than saying "move the defaults block," and the new test cases assert the no-leak behavior for a representative variable from each existing category (a flagged var, a dedicated-machine var, and a memory-gate var) so a regression in any category is caught.

## Migration Plan

No runtime migration — this only changes `install.sh`/`uninstall.sh` script behavior, evaluated fresh on each invocation. No rollback mechanism needed beyond reverting the branch; no persisted state changes shape.
