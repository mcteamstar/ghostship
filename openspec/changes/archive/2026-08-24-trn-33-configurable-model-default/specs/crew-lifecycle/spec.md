## ADDED Requirements

### Requirement: Configurable model default patch
The `_patch_crew_config` function SHALL write `KC_MODEL_DEFAULT` (when set and non-empty) into the crew's `config.local.json` as the `default_model` field inside the `agent` config block. When `KC_MODEL_DEFAULT` is unset or empty, `_patch_crew_config` SHALL NOT write a `default_model` field, leaving KiroCrew's built-in default unchanged. The variable SHALL be documented in `docs/configuration.md`.

The effective model for any given agent is resolved in this precedence order (highest first):
1. `KC_MODEL_OVERRIDE` — transport patches the per-agent `"model"` field directly in every agent JSON file; beats everything
2. Per-agent `"model"` field in the agent JSON (e.g. `academy/agents/*.json`) — explicit per-agent pin
3. `KC_MODEL_DEFAULT` — patched into `config.local.json` as `default_model`; applies when the per-agent field is absent or cleared
4. KiroCrew built-in default — the hardcoded fallback inside KiroCrew when no other override is in effect

#### Scenario: KC_MODEL_DEFAULT set
- **WHEN** the transport is started with `KC_MODEL_DEFAULT=anthropic/claude-sonnet-4`
- **THEN** every new crew's `config.local.json` contains `default_model: "anthropic/claude-sonnet-4"` inside the `agent` block

#### Scenario: KC_MODEL_DEFAULT unset
- **WHEN** the transport is started without `KC_MODEL_DEFAULT`
- **THEN** `_patch_crew_config` does NOT write a `default_model` field into `config.local.json`, leaving KiroCrew's built-in default unchanged

#### Scenario: KC_MODEL_DEFAULT does not affect per-agent pins
- **WHEN** `KC_MODEL_DEFAULT` is set and an agent JSON contains a non-empty `"model"` field (and `KC_MODEL_OVERRIDE` is unset)
- **THEN** that agent continues to use its own pinned model; `KC_MODEL_DEFAULT` only applies to agents whose effective model would otherwise fall through to the KiroCrew built-in

#### Scenario: KC_MODEL_OVERRIDE beats KC_MODEL_DEFAULT
- **WHEN** both `KC_MODEL_OVERRIDE` and `KC_MODEL_DEFAULT` are set
- **THEN** `_patch_models` writes `KC_MODEL_OVERRIDE` into every agent JSON's `"model"` field, making `KC_MODEL_DEFAULT` irrelevant in practice (the per-agent field is now set, so the default is never reached)
