# Proposal

## Why

the local instance currently enables only Kiro, preventing local crews from using the existing Codex backend. Enable Codex alongside Kiro for local development and testing, including correcting the image and login integration defects exposed during activation.

## What Changes

- Add `backends.default: [kiro, codex]` to The local instance’s local `config/ghostship.yaml`.
- Keep Kiro first so crews without an explicit backend retain their default.
- Expose the compatible Codex CLI bundled with `@agentclientprotocol/codex-acp@1.12.0` on PATH in the crew image so the adapter can start `codex app-server`.
- Use `codex login --device-auth` in the transport login flow instead of invoking `codex-acp login`.
- Correct device-code extraction for the CLI’s multiline, ANSI-colored output so the returned URL is accompanied by its one-time code.
- Require Codex’s OS credential-mask sandbox with `sandbox: auto` and no unsandboxed fallback, restoring compatibility with KiroCrew’s enforced permission route.
- Add a checked image compatibility patch for KiroCrew’s unreadable signing-key seal, using descriptor-based mount_setattr while preserving credential isolation and fail-closed behavior.
- Update login unit tests and lifecycle documentation; verify the device URL in a disposable container before installing the fixes with explicit approval.

## Capabilities

### New Capabilities

None. This enables existing multi-backend support and repairs its Codex CLI/login integration.

### Modified Capabilities

None. Backend selection, credential storage, and authentication requirements remain unchanged; the source fixes restore the existing intended behavior; `skip_specs: true` records this deliberate opt-out.

## Impact

The local instance’s ignored local configuration, generated Compose environment, and rebuilt crew image are affected. Source fixes touch `crews/spec-ops/toolchains/codex.sh`, `transport/login.py`, `transport/lifecycle.py` documentation, `tests/unit/test_login.py`, the spec-ops Containerfile and sandbox-seal compatibility helper, and sandbox isolation regression coverage. The toolchain exposes the adapter’s existing compatible dependency rather than adding another independently versioned package. These source fixes will also benefit future installations built from this checkout, but only the local instance is being deployed here. Existing Kiro identity settings, model override, and three-hour timeout are preserved. the production instance is outside deployment scope. Secrets remain in the credential store.
