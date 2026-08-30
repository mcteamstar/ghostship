## Why

Academy assets (agent JSONs, crew manifests, order templates) are loaded with best-effort, silently-skip-on-error semantics. An agent JSON missing the `tools` field is copied into the crew silently — the agent fails at dispatch time inside the container, not at launch. With multiple crew types and operators customising their academy, misconfigured assets become increasingly likely and the failure mode is invisible.

## What Changes

- Add `_validate_academy()` called once at transport startup alongside existing health checks
- Validate every `*.json` in `/agents` parses and has `name`, `description`, `tools` fields
- Validate every manifest lists only agent names that exist in the corresponding academy pool
- Validate every `*.md` in `/orders` has parseable YAML front-matter and at least one `{{...}}` placeholder
- Surface errors as startup warnings (not fatal) so misconfiguration is caught at deploy time, not inside a launched crew
- Add unit tests covering valid/invalid agent JSON and valid/invalid manifest names

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `crew-manifest`: transport startup now validates that every agent name in a manifest exists in the loaded academy pool; a manifest referencing an unknown agent name produces a startup warning

## Impact

- `transport/server.py` — new `_validate_academy()` function called at startup; no changes to crew launch or dispatch paths
- `tests/unit/` — new test cases for validation logic
