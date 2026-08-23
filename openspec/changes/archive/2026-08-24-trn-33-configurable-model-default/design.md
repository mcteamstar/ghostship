## Context

See proposal.md — Why for motivation.

`_patch_crew_config` in `transport/server.py` already writes a batch of KiroCrew fields into `config.local.json` inside each crew container at launch time. The existing `_patch_models` function writes `KC_MODEL_OVERRIDE` directly into each agent JSON's `"model"` field, bypassing the config layer entirely. KiroCrew resolves the effective model per-agent in this order (from its `AgentConfig` loader): per-agent `model` field → `config.json` / `config.local.json` `agent.default_model` → built-in default. The `default_model` field in the `agent` config block is the correct insertion point for a global fallback that still allows per-agent overrides.

The transport already reads `KC_MODEL_OVERRIDE` at the module level (line 107 of `server.py`). The install.sh `--model` flag writes that variable as `-e KC_MODEL_OVERRIDE=…` to the transport container. The pattern is proven and symmetrical.

## Goals / Non-Goals

**Goals:**
- Let operators set a global model fallback via `KC_MODEL_DEFAULT` that applies to agents whose per-agent `model` field would otherwise fall through to the KiroCrew built-in.
- Keep `KC_MODEL_DEFAULT` out of `config.local.json` entirely when the env var is unset, so existing installs see zero behaviour change.
- Expose `KC_MODEL_DEFAULT` through `install.sh --model-default` and the config-file mechanism, consistent with `KC_MODEL_OVERRIDE`.

**Non-Goals:**
- Changing how `KC_MODEL_OVERRIDE` works — it stays as a per-agent JSON patch, not a config field.
- Modifying any agent JSON files at build time.
- Adding per-crew model overrides (that is per-agent JSON, not a transport-level concern).
- Changing the KiroCrew binary's model resolution logic.

## Decisions

### Write `default_model` via `config.local.json`, not by patching agent JSON

`_patch_models` (the existing override path) rewrites every agent JSON file inside the container — it's a blunt instrument appropriate for `KC_MODEL_OVERRIDE`'s "beats everything" semantics. For a *default*, that would break the per-agent field: if we wrote every agent's `"model"` to `KC_MODEL_DEFAULT`, we'd also erase any per-agent pin, defeating the purpose of having a two-level system.

Writing `default_model` to `config.local.json` instead hits KiroCrew's config layer below the per-agent field, giving the correct precedence for free. No changes to agent JSON files, no changes to the KiroCrew binary.

**Alternative considered:** Add a separate Python exec script that only patches agents with no `"model"` field (or with the hardcoded default). Rejected: brittle, depends on knowing what the hardcoded default is, and would break if KiroCrew changes the built-in string. The config field is the clean approach.

### Conditional write: omit the field when `KC_MODEL_DEFAULT` is empty

If we always write `default_model` (even as `""` or `None`), empty values in config.local.json could suppress KiroCrew's built-in default in undefined ways. Only write the field when the env var is set and non-empty. This is consistent with how `KC_MODEL_OVERRIDE` is guarded (`if not model: return`).

### Module-level constant, same pattern as `KC_MODEL_OVERRIDE`

```python
KC_MODEL_DEFAULT = os.environ.get("KC_MODEL_DEFAULT", "")
```

Keeps the code symmetrical and easy to spot. No special-casing needed elsewhere.

### `--model-default` flag in install.sh, parallel to `--model`

The existing `--model` flag maps to `KC_MODEL_OVERRIDE`. `--model-default` maps to `KC_MODEL_DEFAULT`. Both are passed as `-e VAR=value` to the `podman run` command for the transport container. Both are listed in the config-file supported variables table.

## Risks / Trade-offs

**`default_model` key name depends on KiroCrew internals** → The field name `default_model` is read from KiroCrew's `AgentConfig`. If a KiroCrew upgrade renames it, the patch silently stops applying. Mitigation: the field is documented in KiroCrew's config schema; operators would notice on the next KiroCrew version bump. Low risk for a stable, documented config key.

**No validation of the model string at transport startup** → `KC_MODEL_DEFAULT` is written verbatim into `config.local.json`. An invalid model string won't be caught until an agent actually tries to use it. Mitigation: same behaviour as `KC_MODEL_OVERRIDE` today; considered acceptable.

## Migration Plan

No migration needed. `KC_MODEL_DEFAULT` is unset by default — existing installs see no change. Operators who want to use it add `--model-default <model>` to their `install.sh` invocation or `KC_MODEL_DEFAULT=<model>` to their config file, then re-run `install.sh`. Already-running crews are not affected until their next launch (or nuke+relaunch).
