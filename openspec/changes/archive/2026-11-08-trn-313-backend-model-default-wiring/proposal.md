# Proposal

## Why

Explicit backend and global model defaults are resolved by Ghostship but written to `agent.default_model`, a field the installed KiroCrew does not consume. Operators can therefore configure a fallback and still run the harness-selected model, with config-only tests giving false confidence.

## What Changes

- Deliver the resolved backend/global fallback through KiroCrew’s supported `agent.model` field and remove stale generated `agent.default_model` values during configuration patching.
- Preserve precedence for dispatch selections, backend overrides and persona pins; preserve the owning backend’s settings when crews use different backends.
- Keep all shipped model defaults empty and omit model pins from shipped personas, allowing configured fallbacks and harness-owned selection. Ensure operator overrides apply to unpinned personas.
- Add tests that load generated configuration and resolve models through the pinned KiroCrew runtime, plus documentation separating configured fallbacks from harness defaults and rejected-pin behavior.

- Upgrade the pinned Codex ACP adapter to 2.5.0 (KiroCrew-tested 2.x family), retain its bundled CLI, and verify the operator-selected Luna 6 in a fresh local crew.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `yaml-config`: strengthen the per-backend model-control contract with consumable runtime wiring, empty-default behavior and integration verification.

## Impact

Affected areas are crew configuration generation and migration, model-resolution regression tests, and model precedence documentation. YAML keys, environment variable names, MCP signatures, backend order and credentials remain unchanged. Shipped persona prompts and tools remain unchanged; only their model pins are removed. No model is hardcoded in shipped defaults. The user has authorized the adapter upgrade and local installation/verification; remote deployments remain outside scope. Account entitlement checks and rejected-pin fallback remain owned by KiroCrew and the harness.
