## Context

Confirmed against the bundled KiroCrew backend (`kiro_crew` package):

- `POST /api/spawn` (`kiro_crew/dashboard/handlers/messaging.py:api_spawn`) already validates and accepts a `model` field via `SPAWN_RUN_SCHEMA`, passing it to `state.subagents.spawn(..., model=model or None, ...)`. `subagent.py` tracks this as the per-spawn pin (`requested_model`), taking precedence over the agent-config pin (`agent.role_models['subagent']`) when non-empty.
- `POST /api/crons` (`kiro_crew/dashboard/handlers/cron.py:api_crons_create`) independently validates and accepts a `model` field the same way, for scheduled job creation.
- Both endpoints validate `model` with the same rule: `isinstance(str)`, length `<= MAX_SHORT_STRING` (500), and format `_MODEL_NAME_RE = ^[a-zA-Z0-9][a-zA-Z0-9._-]*$`. An "auto" sentinel means explicit inherit (same as unset).

Ghostship's transport builds both request bodies itself (`dispatch()` and `schedule()`/`captain()` in `transport/server.py`) and today never includes a `model` key in either, so the capability exists end-to-end already — it just isn't wired through the transport layer.

Two distinct "config pin" concepts sit below the per-spawn `model` param, and it's important not to conflate them: (1) the persisted agent JSON's own `model` field (`academy/agents/*.json`, e.g. `spectre.json`'s `"model": "gpt-5.6-luna"`), which `KC_MODEL_OVERRIDE` patches in place at crew launch (`_patch_models`, `transport/lifecycle.py:758`); and (2) KiroCrew's own `agent.role_models['subagent']` global fallback (set by `KC_MODEL_DEFAULT`). `subagent.py`'s precedence comment (~line 1230) says the per-spawn `model` wins over "the config pin" whenever non-empty, with no distinction between a persona-authored value and a `KC_MODEL_OVERRIDE`-patched one — both live in the same JSON field. So a per-dispatch `model` outranks *both* tiers, `KC_MODEL_OVERRIDE` included.

## Goals / Non-Goals

**Goals:**
- Let a caller pin the model for exactly one `dispatch` task, or one `schedule`/`captain(order)` recurring job, without touching persona config or crew-wide env vars.
- Fail fast on a malformed `model` value at the transport layer, before any crew API call, consistent with how the transport already validates `agent` (persona allowlist) before contacting the crew.
- Preserve each scheduled job's optional model pin in the transport registry and carry it through restart re-seeding, the transport-owned schedule monitor, and any `fire_immediately` first run so every execution path honors the same job-level choice.

**Non-Goals:**
- No change to model *resolution* precedence for calls that omit `model` — `KC_MODEL_OVERRIDE` > per-agent `model` > `KC_MODEL_DEFAULT` > KiroCrew built-in stays exactly as-is.
- No enforcement of `KC_MODEL_OVERRIDE` as a hard ceiling against a per-call `model`. Explicitly decided against (see Decisions and Risks): a per-dispatch `model` is allowed to outrank `KC_MODEL_OVERRIDE`, matching KiroCrew's own native precedence rather than adding ghostship-side enforcement logic.
- No new model-name allowlist or validation against a live `/api/models` listing — the transport mirrors KiroCrew's own format/length check but does not attempt to duplicate its membership check (KiroCrew's chat model path also skips membership; the runtime is deliberately model-agnostic with a gateway fallback).
- No change to `steer`/`pickup` — model is fixed at spawn/job-creation time only, matching how KiroCrew itself treats it (no "change the model of an already-running session" concept in either endpoint).

## Decisions

**Forward as an optional passthrough field, not a lookup against a local model list.** The transport's job is to get the value to the crew gateway and let the gateway be the single source of truth for what's valid — mirroring how `agent` is validated against the transport's own persona allowlist (a ghostship-owned concept) while `model` is validated only against KiroCrew's generic string-shape rule (a KiroCrew-owned concept). Duplicating KiroCrew's model registry in the transport would drift the moment KiroCrew adds a model.

**Reuse KiroCrew's own validation constants rather than inventing new ones.** The transport-side check mirrors `_MODEL_NAME_RE` and `MAX_SHORT_STRING` exactly, so a value that would be rejected by the crew gateway is rejected at the transport with the same shape of error, just earlier (no wasted round trip to a possibly-idle crew).

**`captain(action="order")` accepts `model` only on the create-new-job path.** Resuming a paused check-in reuses the existing job as-is (same pattern the existing `fire_immediately` parameter already follows for resume) — there is no job body to attach `model` to on a resume, since no new `/api/crons` call is made.

**Let a per-dispatch `model` outrank `KC_MODEL_OVERRIDE` rather than build enforcement against it.** This matches KiroCrew's own native precedence (the per-spawn pin always wins over the config pin, regardless of how that config pin was set) instead of adding ghostship-side logic to detect the crew's configured `KC_MODEL_OVERRIDE` at dispatch time and reject or strip a conflicting per-call `model`. Simpler, and consistent with treating `model` as a pure passthrough (see the first Decision above) rather than a value the transport reasons about. The trade-off is real and is not hidden: `KC_MODEL_OVERRIDE` stops being an absolute ceiling once this ships. Documented explicitly in proposal.md and below.

**Carry schedule pins through every transport-owned execution path.** A schedule's gateway job is durable inside the crew, but Ghostship also keeps a registry entry for restart bootstrap and its own idle-crew schedule monitor. The optional `model` is stored alongside the existing message, agent, and schedule fields; re-seeding includes it when a gateway job is missing, and the monitor includes it on its direct `/api/spawn` tick. `fire_immediately` is another direct spawn rather than a gateway cron tick, so it receives the same model when one was supplied. On Captain resume, the caller's new `model` remains ignored; an existing registry pin is preserved instead.

**Alternatives considered:**
- *Add a `set_model`-style follow-up call after spawn instead of a create-time field* — rejected: KiroCrew's own contract for this is create-time only (`api_spawn`/`api_crons_create`), and `subagent.py`'s explicit distinction between `model` (requested) and `resolved_model` (served) exists precisely to audit a *pinned* run, not a run whose model changed mid-session.
- *Only add `model` to `dispatch`, leave `schedule`/`captain` out of scope* — rejected: `/api/crons` already validates and accepts the identical field, so leaving it out would be an arbitrary gap for no implementation-cost saving.
- *Enforce `KC_MODEL_OVERRIDE` as a hard ceiling (reject/strip a conflicting per-call `model`)* — considered and rejected: would require the transport to read back the crew's configured override at dispatch time (not currently tracked per-crew outside the env var used at launch), adds a second source of truth to keep in sync with what `_patch_models` actually wrote, and diverges from KiroCrew's own resolution semantics for no clearly-requested benefit. Revisit if `KC_MODEL_OVERRIDE` is actually being relied on as an administrative/cost-control ceiling in practice.

## Risks / Trade-offs

[A per-dispatch `model` silently bypasses a crew-wide `KC_MODEL_OVERRIDE`] → Accepted trade-off, not mitigated in code. `KC_MODEL_OVERRIDE` was previously an absolute ceiling (nothing could set a *different* per-agent model without editing the crew's launch config); after this change, any caller with dispatch access can override it per-call. Document this loudly in the `dispatch`/`schedule`/`captain` docstrings and the `ghostship-command` skill so an operator relying on `KC_MODEL_OVERRIDE` for cost or policy control knows it is no longer absolute.

[KiroCrew changes or removes `model` validation in a future release] → Low risk: this passthrough has no local allowlist to go stale; a future incompatible KiroCrew change would surface as a validation error from the crew gateway itself, same as any other passthrough field.

[Caller expects `model` to also apply to `steer`/`continue` on the same task] → Document explicitly in the `dispatch`/`schedule`/`captain` docstrings and the `ghostship-command` skill that `model` is spawn/job-creation-time only, not a live session property.

## Migration Plan

Additive, backward-compatible: `model` is optional on all three tools, defaults to omitted (no behavior change for existing callers). No data migration. Ship as a single change; no phased rollout needed.
