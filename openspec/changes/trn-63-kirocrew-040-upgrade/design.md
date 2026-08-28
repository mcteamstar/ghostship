## Context

See proposal.md — Why for the full motivation. KiroCrew 0.4.0 introduces four breaking changes in its API and configuration layer. This design covers how ghostship's transport adapts to each, plus two improvements to leverage.

## Goals / Non-Goals

**Goals:**
- Ghostship crews launch and configure correctly on KiroCrew 0.4.0
- All four breaking changes resolved without regressions to the existing fleet lifecycle
- Reload-in-place replaces stop/start where applicable

**Non-Goals:**
- Deep refactor of the bootstrap sequence beyond what 0.4.0 requires
- Changing the crew container image build process beyond the version pin

## Open Questions

1. ~~**OQ-1**: What is the exact agent template name to pass in `POST /api/chat/slots`?~~ **Resolved**: use `"kirocrew"` (the built-in default). This is a bootstrapping placeholder — `_copy_agents()` runs pre-gateway and overwrites the defaults with ghostship's custom agent JSONs before any dispatch ever occurs. The `"kirocrew"` template is never called in practice.
2. ~~**OQ-2**: What is the reload-in-place endpoint path?~~ **Resolved**: `POST /api/chat/slots/{slot}/reload` — no request body. Confirmed in `src/kiro_crew/dashboard/routes/chat.py:83`. Returns 409 if a turn is in flight or subagents are attached. Conversation history preserved across reload.
3. **OQ-3**: Does `spawn_min_memory_gb: 0` still work in 0.4.0 or has a floor been added? If floored, use `admission_gate: false` instead. Verify before task 5.1.

## Decisions

### D1: Pass `"agent": "kirocrew"` on crew creation

**Decision:** Add `"agent": "kirocrew"` to the `POST /api/chat/slots` payload in `_finish_crew_setup()`. `"kirocrew"` is the built-in default template and satisfies the 0.4.0 requirement. It acts as a bootstrapping placeholder only — `_copy_agents()` runs pre-gateway and overwrites the defaults with ghostship's custom agent JSONs before any dispatch ever occurs.

**Rationale:** Minimal change — one field addition to the existing creation call. The `"kirocrew"` template is never called in practice after the custom agents are in place.

### D2: Keep `_copy_agents()` as filesystem writes, move timing before gateway start

**Decision:** Do not switch `_copy_agents()` to `POST /api/agents`. Instead, confirm (and enforce if needed) that all agent JSON copies happen before the gateway starts. The bootstrap sequence already writes files before the first `_wait_gateway` call — verify this is true and add an assertion if not.

**Alternatives considered:**
- *Switch to `POST /api/agents`*: Adds API dependency and changes the bootstrap contract. Unnecessary if the copies already happen pre-gateway, which is the likely case.

**Rationale:** Filesystem writes pre-gateway-start are explicitly allowed by the 0.4.0 spec. The existing timing is almost certainly correct — the verification step is low cost.

### D3: Audit bounds before writing; clamp only within allowed range

**Decision:** Read the current config values ghostship writes in `_patch_crew_config()` and `_patch_models()` and verify each against the 0.4.0 bounds table. Where ghostship writes a value that could be user-configurable (e.g. via a GA_* env var), add a clamp before the API call rather than letting the API reject it.

**Rationale:** Returning a 4xx from a config write mid-bootstrap would fail the crew launch silently. Defensive clamping at the ghostship layer gives a clear error path.

### D4: Apply `os.path.expandvars()` before all config path writes

**Decision:** Wrap any string that could contain a `$VAR` reference with `os.path.expandvars()` before passing it to a KiroCrew config API. This is a blanket defensive fix — grep `_patch_crew_config` and `_patch_models` for `$` occurrences and apply where found.

**Rationale:** Belt-and-suspenders. If any path contains an env var reference today, 0.4.0 would reject it. Expanding unconditionally is safe (no-op on strings without `$`).

### D5: Add `"poolable": false` to ghostship's MCP server in `mcp.json`

**Decision:** The ghostship MCP server (`mcp.json`) exposes tools that are entirely stateless (no per-session state). No `"poolable": false` is needed. Audit the server's `env` block — if it declares env vars, confirm they are session-agnostic before leaving pooling enabled.

**Rationale:** Ghostship's MCP tools operate on the transport's shared registry; there is no per-connection state. Pooling is safe and reduces overhead.

### D6: Replace `_ensure_crew_running` stop/start with reload-in-place

**Decision:** Replace the stop/start cycle in `_ensure_crew_running` with a call to `POST /api/chat/slots/{slot}/reload` when the container is already running and only a config refresh is needed. Keep stop/start for cold-boot (container stopped or dead). The endpoint returns 409 if a turn is in-flight — handle gracefully by falling back to stop/start in that case.

**Rationale:** Reload-in-place preserves slot identity and avoids the cold-start cost. The endpoint is confirmed at `POST /api/chat/slots/{slot}/reload` (no request body required).

## Migration Plan

1. Pin Containerfiles to `kirocrew:0.4.0`
2. Resolve OQ-1, OQ-2, OQ-3 from the 0.4.0 release notes
3. Apply D1–D5 in `transport/server.py`
4. Apply D6 if OQ-2 is resolved
5. Integration test: full fleet lifecycle (launch, dispatch, pickup, nuke)
