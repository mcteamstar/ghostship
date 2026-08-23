## Why

`_patch_crew_config` already writes a batch of KiroCrew config fields into each crew at launch time via `config.local.json`, yet there is no way to set a global model fallback short of rewriting every agent JSON file. `KC_MODEL_OVERRIDE` fills the top of the precedence stack (hard-overrides all agents), but the bottom of the stack — below the per-agent `"model"` field — is an undocumented hardcoded string (`"gpt-5.6-luna"`) buried inside the KiroCrew binary. Operators who want to run all agents on a different base model without pinning every individual agent JSON have no supported path.

## What Changes

- Add `KC_MODEL_DEFAULT` environment variable to the transport; read at startup alongside the existing `KC_MODEL_OVERRIDE`.
- In `_patch_crew_config`, write `KC_MODEL_DEFAULT` (when set) into the crew's `config.local.json` as the `default_model` field in the `agent` config block — the KiroCrew field that sits below the per-agent `"model"` field in precedence.
- Expose `KC_MODEL_DEFAULT` in `install.sh` help text and `--model-default` flag (parallel to the existing `--model` flag for `KC_MODEL_OVERRIDE`).
- Document `KC_MODEL_DEFAULT` in `docs/configuration.md` alongside `KC_MODEL_OVERRIDE`, with the full four-level precedence order.
- Document `KC_MODEL_DEFAULT` in `config/ghostship.conf.example`.
- When `KC_MODEL_DEFAULT` is unset (the common case), `_patch_crew_config` writes nothing for `default_model` — no change in behaviour for existing installs.

**Precedence order** (highest → lowest):
1. `KC_MODEL_OVERRIDE` → patches per-agent `"model"` fields directly, beats everything
2. Per-agent `"model"` field in `academy/agents/*.json` → explicit per-agent pin
3. `KC_MODEL_DEFAULT` → patched into `config.local.json` as `default_model`
4. KiroCrew internal default (currently `"gpt-5.6-luna"`)

## Capabilities

### New Capabilities

_(none — this is a configuration extension, not a new behavioural capability)_

### Modified Capabilities

- `crew-lifecycle`: `_patch_crew_config` gains a new conditionally-written `default_model` field in the `agent` config block, driven by `KC_MODEL_DEFAULT`
- `installation`: `install.sh` gains a `--model-default` flag and `KC_MODEL_DEFAULT` is added to the config-file variable table; `docs/configuration.md` gains a new row

## Impact

- `transport/server.py` — one new module-level constant (`KC_MODEL_DEFAULT`), two lines in `_patch_crew_config`
- `install.sh` — new `--model-default` flag, help text, pass-through to `-e KC_MODEL_DEFAULT=…`
- `docs/configuration.md` — one new table row
- `config/ghostship.conf.example` — one new commented-out line
- `transport/test_transport.py` — extend the existing `_patch_crew_config` test to cover the conditional `default_model` field
