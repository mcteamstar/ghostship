# Proposal

## Why

The current `backends.default` list conflates two separate concepts: selecting the
implicit runtime backend and selecting which optional backend toolchains are bundled.
Kiro is intentionally built in, but Claude and Codex enablement is not expressed by
the presence of their backend configuration sections.

## What Changes

- **BREAKING** Change `backends.default` from a list to a scalar backend name.
- Keep Kiro implicitly enabled as the built-in backend and use `kiro` as the scalar default when `backends.default` is omitted.
- Use the presence of optional `backends.claude` and `backends.codex` configuration sections to determine which additional toolchains are enabled and bundled.
- Permit an empty mapping such as `backends.claude: {}` to opt into a backend while inheriting its built-in model and runtime defaults.
- Preserve the scalar default backend as the backend used when `launch()` omits `backend`.
- Set explicit backend model defaults for all three supported backends: `claude-haiku-5.5` for Kiro, `claude-haiku-5-5` for Claude, and `gpt-6-luna` for Codex.
- Keep shipped personas unpinned so backend defaults prevent expensive automatic model routing without becoming per-agent hard pins.
- Update install-time environment generation, runtime backend validation, examples, documentation, tests, and compatibility handling.
- Reject or clearly migrate the old list form instead of treating it as the enabled-backend configuration.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `yaml-config`: Change backend selection and enablement semantics.
- `agent-backends`: Derive enabled backends from configured backend sections rather than an ordered list and implicit Kiro inclusion.
- `crew-acp-backend`: Validate and launch only backends enabled by configuration, with the scalar default used for implicit launches.

## Impact

Affected areas include `bin/lib/yaml_config.py`, installer/toolchain build logic,
transport backend parsing and launch validation, the YAML example and configuration
documentation, OpenSpec requirements, and unit/integration tests. Existing operator
configs using the list form require migration to a scalar default plus explicit
backend sections.
