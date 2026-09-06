## MODIFIED Requirements

### Requirement: Containerfiles pin to kirocrew:0.5.0

All ghostship Containerfiles that reference the KiroCrew base image SHALL pin
to `kirocrew:0.5.0`. A Containerfile left pinned at `0.4.x` or `latest` will
pull an incompatible base image.

#### Scenario: Containerfile updated to 0.5.0 pin
- **WHEN** a ghostship Containerfile is built after this change
- **THEN** it resolves `FROM ghcr.io/kirodotdev/kirocrew:0.5.0` as the base
  layer and the resulting image is compatible with the 0.5.0 API surface

#### Scenario: Old pin triggers build failure
- **WHEN** a Containerfile still references `kirocrew:0.4.x` or `kirocrew:latest`
  after this change is applied
- **THEN** the build CI job fails or the resulting image is flagged as
  incompatible during the regression test pass

### Requirement: Configurable spawn_min_memory_gb patch

The `_patch_crew_config` function SHALL write `GA_SPAWN_MIN_MEMORY_GB` (default
1.5) into the crew's `spawn_min_memory_gb` config field instead of the
hardcoded value `0`.

The `spawn_min_memory_gb` field SHALL be written as a native config file entry
(not via a runtime workaround) because KiroCrew 0.5.0 fixes the loader that
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
  KiroCrew 0.5.0 reads `spawn_min_memory_gb` from the config file correctly

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
    runtime in KiroCrew 0.5.0
12. Mint session cookie
13. Read version label, write registry entry

#### Scenario: Agent files written before runtime write-protection
- **WHEN** `_copy_agents` is called during crew setup
- **THEN** the agent JSON files are written to `KIRO_AGENTS_DIR` during the
  post-restart gateway startup window, before KiroCrew 0.5.0 makes that
  directory write-protected at runtime
