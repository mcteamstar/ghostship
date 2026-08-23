## 1. Transport changes

- [ ] 1.1 In `_patch_crew_config`, read `GA_SUBAGENT_TIMEOUT_SECS` env var (default 3600) and add `subagent_timeout_secs` to the config patch dict
- [ ] 1.2 In `_patch_crew_config`, read `GA_SUBAGENT_MAX_TURNS` env var (default 200) and add `subagent_max_turns` to the config patch dict

## 2. Tests

- [ ] 2.1 Update the existing `_patch_crew_config` test to assert `subagent_timeout_secs` and `subagent_max_turns` are present with correct defaults
- [ ] 2.2 Add test: `GA_SUBAGENT_TIMEOUT_SECS=7200` in env → `subagent_timeout_secs: 7200` in patched config
- [ ] 2.3 Add test: `GA_SUBAGENT_MAX_TURNS=300` in env → `subagent_max_turns: 300` in patched config

## 3. Documentation

- [ ] 3.1 Add `GA_SUBAGENT_TIMEOUT_SECS` entry to `docs/configuration.md` config-file variables table (default: 3600, no install.sh flag)
- [ ] 3.2 Add `GA_SUBAGENT_MAX_TURNS` entry to `docs/configuration.md` config-file variables table (default: 200, no install.sh flag)

## 4. Validation

- [ ] 4.1 Run targeted tests: `python -m unittest transport.test_transport.PatchCrewConfigTests -v` (or equivalent class name)
- [ ] 4.2 Run `openspec validate --specs` to confirm spec coherence
