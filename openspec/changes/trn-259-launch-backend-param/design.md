# Design

## Context

See proposal.md for motivation. The backend is currently a module-level constant, `GA_CREW_ACP_BACKEND = cfg.ga_crew_agent.split(",")[0]`, computed separately in `tools.py`, `lifecycle.py` and `server.py`, and imported into `launcher.py`. Every per-backend branch in the launch path reads it directly:

- `tools.launch`: enabled check, credential lookup, not-authenticated login flow, container env injection.
- `launcher.finish_setup`: post-start auth injection (claude `oauth`, codex `chatgpt`) and `Crew(acp_backend=...)`.
- `lifecycle._patch_crew_config`: writes `acp_backend` and `default_model` into `config.local.json`.
- `lifecycle._patch_models`: the per-backend model override.
- Two restart paths in `launcher.py` (the concurrent-restart path around line 386 and the reconcile restart around line 783) call `_patch_crew_config(podman, container)` with no backend, so they re-apply the **current default**. That's a latent bug today (changing the default and reinstalling flips the runtime of existing crews on their next restart) and becomes a real one once crews can differ.

`Crew.acp_backend` already exists and round-trips through the registry, defaulting to `"kiro"` for old entries. `captain_engine` and the claude/codex logout wipes already read the per-crew value.

The enabled set is `{kiro} ∪ GA_CREW_AGENT`; the crew image bakes toolchains for exactly that set, so it is also the set of backends a crew can physically run.

## Goals / Non-Goals

**Goals:**
- One resolved `backend` value flows explicitly through the launch path; no code in the launch or restart path reads the global constant except to supply the default.
- Restarts read the backend from the crew record.

**Non-Goals:**
- Removing `GA_CREW_ACP_BACKEND` as the default, or changing how `backends.default` is configured.
- Per-backend images. All enabled toolchains stay in one image.

## Decisions

**Parameter name `backend`.** `agent` is already the persona argument on `dispatch`, and `acp_backend` leaks an internal term. `backend` matches `backends.default` in the yaml and `ghostship auth login <backend>`.

**Resolve once in `tools.launch`, pass explicitly.** `launch` lower-cases and validates the argument (or takes the default), then passes `backend=` to `finish_setup`, `_patch_crew_config` and `_patch_models`, and uses it for the existing credential and env-injection branches. Alternative considered: stash it on a thread-local or the composition entry. Rejected: implicit, and it would not reach the restart paths.

**`_patch_crew_config` and `_patch_models` take a required `backend` keyword.** Making it required (no default) forces every call site, including the two restart paths, to pass something deliberate. The restart paths pass `c.acp_backend or "kiro"`. Alternative: default to `GA_CREW_ACP_BACKEND`. Rejected: that is exactly the silent fallback that causes the restart bug.

**Validation error shape.** Return `{"error": "backend_not_enabled", "backend": <requested>, "enabled": [...], "instructions": ...}`, reusing `login._backend_not_enabled_message` for the instructions so the remedy text stays in one place. An unrecognised name gets the same shape; there is no reason to distinguish "unknown" from "not enabled" for the caller.

**New backends plug in through the enabled set.** Validation uses the same enabled-set check as login (`login._backend_enabled`), not a hard-coded list, so a backend added later (e.g. opencode in the in-flight `trn-168-opencode-backend-support` change) becomes launchable once it is enabled and has its credential and env-injection branch. Whichever of the two changes lands second adds its backend's branch to the per-crew path.

**Leave kiro-login injection into running crews alone.** Kiro login completion injects auth rows into every running crew. Claude and codex crews also bundle kiro-cli, so this is harmless, and the in-flight `logout-cancels-pending-login` change already rewrites that requirement. Filtering by backend here would conflict with it for no user-visible gain.

## Risks / Trade-offs

- [A call site of `_patch_crew_config`/`_patch_models` is missed] → making `backend` a required keyword turns a miss into a `TypeError` caught by the unit suite rather than a silent default.
- [Restart behaviour changes for existing crews whose recorded backend differs from the current default] → this is the intended fix; old entries without `acp_backend` keep running as kiro, which is what they were launched as (pre-TRN-167 crews were all kiro).
- [Captain or CLI users can't pick a backend yet] → out of scope; they keep getting the default, so nothing regresses.

## Migration Plan

Additive MCP parameter; no config or registry migration. Existing callers keep the default. Rollback is a revert: crews launched on a non-default backend keep working until restarted, after which an old transport re-patches them to the default (the pre-existing behaviour).
