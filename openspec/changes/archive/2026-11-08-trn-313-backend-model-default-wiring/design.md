# Design

## Context

See proposal.md. Ghostship resolves YAML into `KC_MODEL_<B>_DEFAULT` and `KC_MODEL_DEFAULT`, then `_patch_crew_config` emits the chosen value as `agent.default_model`. Inspection of the pinned KiroCrew image confirms its AgentConfig supports `model` and has no `default_model` field. Its resolver places named persona/member selections above the global `agent.model` fallback. The current tests inspect generated structures but do not prove that downstream loading consumes this field.

All shipped personas currently pin a model from another provider family. In the observed Codex session the pin was refused after model-list validation and the session stayed on the harness-selected default. This illustrates two stages, not a single fallback loop: Ghostship configuration resolution followed by upstream namespace/availability handling. Instance names, task IDs, credentials and actual device codes are intentionally excluded from these artifacts.

## Goals / Non-Goals

**Goals:** Make supported explicit defaults effective in the pinned runtime, preserve model precedence, and prove all-empty behavior without hardcoding any model.

**Non-Goals:** Change persona prompts/tools, default backend order, entitlement behavior, model translation/routing, override semantics, reasoning-effort selection, or public response schemas. No concrete model pin or new upstream patch is required. Actual-model dashboard/API reporting and automatic retry through lower tiers after an unavailable pin are separate work.

## Decisions

1. **Use the supported downstream field.** Continue resolving backend default before global default, but write the result to `agent.model`. Do not write both fields: duplicate unsupported state masks future drift. Use the pinned KiroCrew loader and resolver as the authoritative compatibility contract rather than only matching our generated JSON.
2. **Preserve inheritance.** Named persona/member pins remain above the generated global fallback; dispatch selections and the existing backend override mechanism retain their priority. Use supported fixture models on the tested backend to distinguish precedence from namespace filtering or entitlement refusal. User explicitly requested backend-neutral shipped personas after live verification. Remove their model fields, while preserving precedence for operator-authored persona pins.
3. **Own generated-state migration.** Extend configuration patching to remove legacy generated `agent.default_model`. Set generated `agent.model` to the resolved fallback, or the upstream `auto` sentinel when backend and global fallbacks are empty. This clears a previously generated fallback while leaving operator YAML and credentials untouched. Changes to hand-edited generated crew config are not persistent operator configuration.
4. **Test the actual consumer.** Add disposable-image integration coverage loading generated config with pinned KiroCrew and resolving the requested model without calling model providers. Cover backend/global/empty values, supported persona pins, dispatch selections, existing override behavior, different crew backends, legacy cleanup and clear/reapply. Unit tests retain fast coverage of generated patch payloads and migrations. Provider availability and actual billing are not inferred from configuration-only tests.
5. **Keep shipped defaults empty and personas backend-neutral.** Remove explicit model fields from the six shipped persona files. Apply backend overrides to unset/auto persona files as well, since the old patch script skipped those files. Preserve operator override priority and test it across all backends.
6. **Keep fallback settings empty.** Built-in values and the example stay `""` for every backend and the global fallback. Do not copy any local operator model choice into shipped defaults or test expectations. Documentation explains that backend order selects a harness, `model.default` supplies a fallback, and neither promises a particular harness model or complexity-based routing.

7. **Align the Codex toolchain.** Upgrade codex-acp from 1.12.0 to 2.5.0, matching KiroCrew’s tested 2.x family. Continue exposing the CLI supplied by that adapter rather than installing a second independently versioned CLI. Earlier UI/temporary CLI diagnosis proved the saved login can access Luna 6 on the newer catalogue; acceptance requires a fresh KiroCrew session, not only a direct CLI request. Local installation is authorized by the user.

## Risks / Trade-offs

- [Correctly consumed defaults change behavior for operators whose settings were previously ignored] → Document the fix and preserved precedence; test cross-backend isolation and migration.
- [Higher-precedence unavailable pins can still leave the session on a harness default] → Explicitly document this boundary; do not claim the field fix also adds a fallback retry ladder.
- [Consumer drift or namespace differences] → Run integration tests against the pinned image and use supported fixture model IDs, not account-dependent live defaults.
- [Existing generated fallback survives clearing configuration] → Test clear/reapply and legacy key removal, including idempotent repeat application.

## Migration Plan

The user authorized local installation and fresh-session verification. For any remote rollout requiring separate approval, reinstall the transport and reapply generated configuration through supported crew lifecycle operations; already-running providers may retain their model until a new session/process is created. Do not nuke existing workspaces to activate this fix. Back up generated configuration before any runtime migration. To roll back, restore prior transport code and regenerate from operator YAML with deployment approval. The YAML schema, credential store and backend order do not change.
