# Tasks

## 1. Config Resolution and Migration

- [x] 1.1 Change YAML normalization so `backends.default` is a validated scalar backend name defaulting to `kiro`, derive optional enabled backends from present Claude/Codex sections while retaining implicit Kiro, and reject legacy list values with migration guidance; verify with focused `yaml_config` unit tests.
- [x] 1.2 Preserve optional backend-section presence through layered default/repo/XDG resolution, treat explicit empty mappings (`claude: {}` / `codex: {}`) as opt-ins inheriting built-in defaults, and avoid allowing built-in empty fields to enable toolchains; verify minimal, repo, XDG, and `--config` fixture cases.
- [x] 1.3 Update installer environment and toolchain build generation to use the normalized enabled set while retaining the scalar default separately; verify generated compose/build arguments for Claude-only, Kiro+Claude, and Codex-enabled configurations.

## 2. Runtime Backend Selection

- [x] 2.1 Retain implicit Kiro in runtime backend parsing, validate the scalar default against the enabled set, and default it to Kiro; verify startup/configuration unit tests for absent, present, duplicate, and unknown optional backends.
- [x] 2.2 Update launch, login, credential, and inert-setting validation to use the section-derived enabled set and preserve explicit per-crew backend selection; verify enabled and disabled backend scenarios.
- [x] 2.3 Update backend-related runtime tests and integration tests to assert that an absent optional backend cannot launch, login, or require a bundled toolchain, while built-in Kiro and present optional backends can.

## 3. Schema, Documentation, and Examples

- [x] 3.1 Update `config/ghostship.yaml.example`, configuration docs, and migration/troubleshooting guidance to show scalar `backends.default` and backend-section enablement; verify the example matches the parser’s supported fields.
- [x] 3.2 Update the main OpenSpec YAML/config/backend requirements and remove contradictory list-order semantics while retaining implicit Kiro; verify `openspec validate --strict` passes.
- [x] 3.3 Set backend model defaults to `claude-haiku-5.5` for Kiro, `claude-haiku-5-5` for Claude, and `gpt-6-luna` for Codex; keep shipped personas unpinned and verify all three backend model fallbacks avoid `auto` routing.

## 4. Integration Verification

- [x] 4.1 Run the complete relevant unit and integration test suites and verify no backend-selection, image-build, or config migration regressions remain.
- [x] 4.2 Run a local install using the migrated config, verify the generated toolchain set and default backend through a live launch/crew inspection, and record the result.
