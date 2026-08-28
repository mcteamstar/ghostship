## MODIFIED Requirements

### Requirement: Crew setup completion is all-or-nothing
The system SHALL only mark a crew "running" after all required setup steps have
succeeded, and SHALL clean up the crew if any required step fails. Auth injection
SHALL be verified by exit code, not by pattern-matching the output string.

The setup steps SHALL execute in dependency order:

1. Wait for gateway (pre-restart)
2. Inject kiro-cli auth (`_inject_auth`)
3. Generate and inject admiral signing secret — alongside auth, before restart,
   so the secret is in place before Raven can ever run
4. Patch crew config (`_patch_crew_config`) — including the required `agent`
   field sourced from `GA_CREW_AGENT` (default: `"kiro"`)
5. Container restart (auth + config take effect)
6. Wait for gateway (post-restart)
7. Copy agents, skills, steering
8. Seed OpenSpec store
9. Inject security policy (depends only on admiral secret, not on the gateway)
10. Wait for KiroCrew to seed built-in agent files (gateway-dependent)
11. Patch model overrides — write `agents` directory files **before** calling
    any gateway endpoint, because the agents directory is write-protected at
    runtime in KiroCrew 0.4.0
12. Mint session cookie
13. Read version label, write registry entry

The admiral signing secret write SHALL use `os.fsync` before closing the file
descriptor to ensure the write is durable before any process inside the container
can read the file.

The `_patch_crew_config` call in step 4 (pre-restart) SHALL write the `agent`
field into `config.local.json` so the gateway picks it up on first start. The
field SHALL be sourced from the `GA_CREW_AGENT` transport environment variable
(default: `"kiro"`).

The `_copy_agents` call (step 7) — and any other setup step that writes agent
JSON files into `KIRO_AGENTS_DIR` — SHALL occur **after** the post-restart
gateway is ready and SHALL NOT be called after the gateway is already serving
requests, because KiroCrew 0.4.0 makes the agents directory write-protected at
runtime.

#### Scenario: Successful setup
- **WHEN** all setup steps succeed
- **THEN** the crew is marked "running" and the admiral secret is present in the
  container before the post-restart gateway ever becomes reachable

#### Scenario: Admiral secret present before post-restart gateway
- **WHEN** the transport has completed auth injection and the pre-restart gateway
  wait, and then restarts the container
- **THEN** the admiral secret file exists at
  `/home/kirocrew/.kiro/crew/.admiral_secret` before any post-restart gateway
  call is made

#### Scenario: Cookie mint fails
- **WHEN** every step up to and including cookie minting succeeds except
  `_mint_cookie`
- **THEN** the crew is cleaned up and `launch` returns an error

#### Scenario: Auth injection failure is detected
- **WHEN** the auth injection command exits with a non-zero exit code
- **THEN** the system treats the injection as failed, does not proceed with the
  remaining setup steps, and tears down the partially-created crew

#### Scenario: Auth injection output is not used as a success signal
- **WHEN** the auth injection command exits with a non-zero exit code but its
  output contains the word "injected"
- **THEN** the system treats the injection as failed, not as successful

#### Scenario: Agent files written before runtime write-protection
- **WHEN** `_copy_agents` is called during crew setup
- **THEN** the agent JSON files are written to `KIRO_AGENTS_DIR` during the
  post-restart gateway startup window, before KiroCrew 0.4.0 makes that
  directory write-protected at runtime

### Requirement: Configurable spawn_min_memory_gb patch
The `_patch_crew_config` function SHALL write `GA_SPAWN_MIN_MEMORY_GB` (default
1.5) into the crew's `spawn_min_memory_gb` config field instead of the
hardcoded value `0`.

The `spawn_min_memory_gb` field SHALL be written as a native config file entry
(not via a runtime workaround) because KiroCrew 0.4.0 fixes the loader that
previously ignored this field in config files.

#### Scenario: Default spawn threshold
- **WHEN** `GA_SPAWN_MIN_MEMORY_GB` is not set
- **THEN** `spawn_min_memory_gb` is patched to `1.5`

#### Scenario: Custom spawn threshold
- **WHEN** `GA_SPAWN_MIN_MEMORY_GB` is set to `2.0`
- **THEN** `spawn_min_memory_gb` is patched to `2.0`

#### Scenario: spawn_min_memory_gb zero is a valid disable sentinel
- **WHEN** `GA_SPAWN_MIN_MEMORY_GB` is set to `0`
- **THEN** `spawn_min_memory_gb` is patched to `0` in the config, disabling
  the spawn memory gate inside the crew

#### Scenario: spawn_min_memory_gb written via config file, not workaround
- **WHEN** a stopped crew container is restarted via `_ensure_crew_running`
- **THEN** the stop/start/patch/stop/start workaround sequence is NOT executed;
  instead a single `_patch_crew_config` + restart sequence is used, because
  KiroCrew 0.4.0 reads `spawn_min_memory_gb` from the config file correctly

### Requirement: Configurable model default patch
The `_patch_crew_config` function SHALL write `KC_MODEL_DEFAULT` (when set and
non-empty) into the crew's `config.local.json` as the `default_model` field
inside the `agent` config block. When `KC_MODEL_DEFAULT` is unset or empty,
`_patch_crew_config` SHALL NOT write a `default_model` field, leaving KiroCrew's
built-in default unchanged. The variable SHALL be documented in
`docs/configuration.md`.

The `_patch_crew_config` function SHALL also write the `agent` field into the
`agent` config block, sourced from `GA_CREW_AGENT` (default: `"kiro"`). KiroCrew
0.4.0 requires this field to be present in `config.local.json`; crew creation
fails at the gateway with a 4xx if it is absent at the time the config is read.

The effective model for any given agent is resolved in this precedence order
(highest first):
1. `KC_MODEL_OVERRIDE` — transport patches the per-agent `"model"` field
   directly in every agent JSON file; beats everything
2. Per-agent `"model"` field in the agent JSON (e.g. `academy/agents/*.json`)
   — explicit per-agent pin
3. `KC_MODEL_DEFAULT` — patched into `config.local.json` as `default_model`;
   applies when the per-agent field is absent or cleared
4. KiroCrew built-in default — the hardcoded fallback inside KiroCrew when no
   other override is in effect

#### Scenario: KC_MODEL_DEFAULT set
- **WHEN** the transport is started with `KC_MODEL_DEFAULT=anthropic/claude-sonnet-4`
- **THEN** every new crew's `config.local.json` contains
  `default_model: "anthropic/claude-sonnet-4"` inside the `agent` block

#### Scenario: KC_MODEL_DEFAULT unset
- **WHEN** the transport is started without `KC_MODEL_DEFAULT`
- **THEN** `_patch_crew_config` does NOT write a `default_model` field into
  `config.local.json`, leaving KiroCrew's built-in default unchanged

#### Scenario: agent field required in config
- **WHEN** `_patch_crew_config` writes `config.local.json`
- **THEN** the `agent` config block includes an `agent` field set to the value
  of `GA_CREW_AGENT` (default `"kiro"`), satisfying KiroCrew 0.4.0's
  required-field check

#### Scenario: GA_CREW_AGENT unset uses default
- **WHEN** `GA_CREW_AGENT` is not set
- **THEN** `_patch_crew_config` writes `"agent": "kiro"` into the config block

#### Scenario: KC_MODEL_DEFAULT does not affect per-agent pins
- **WHEN** `KC_MODEL_DEFAULT` is set and an agent JSON contains a non-empty
  `"model"` field (and `KC_MODEL_OVERRIDE` is unset)
- **THEN** that agent continues to use its own pinned model; `KC_MODEL_DEFAULT`
  only applies to agents whose effective model would otherwise fall through to
  the KiroCrew built-in

#### Scenario: KC_MODEL_OVERRIDE beats KC_MODEL_DEFAULT
- **WHEN** both `KC_MODEL_OVERRIDE` and `KC_MODEL_DEFAULT` are set
- **THEN** `_patch_models` writes `KC_MODEL_OVERRIDE` into every agent JSON's
  `"model"` field, making `KC_MODEL_DEFAULT` irrelevant in practice (the
  per-agent field is now set, so the default is never reached)
