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

1. **OQ-1**: What is the exact agent template name to pass in `POST /api/chat/slots`? Likely `"kirocrew"` but must be confirmed from the 0.4.0 changelog or source. Blocks D1.
2. **OQ-2**: What is the reload-in-place endpoint path? (`POST /api/chat/slots/{id}/reload`? `PATCH /api/sessions/{id}`?) Must be confirmed from 0.4.0 release notes. Blocks D6.
3. **OQ-3**: Does `spawn_min_memory_gb: 0` still work in 0.4.0 or has a floor been added? If floored, use `admission_gate: false` instead. Verify before task 5.1.

## Decisions

### D1: Pass `"agent": "kirocrew"` on crew creation (pending OQ-1)

**Decision:** Add `"agent": "<template-name>"` to the `POST /api/chat/slots` payload in `_finish_crew_setup()` (or wherever ghostship creates the initial crew slot). Default value `"kirocrew"` pending OQ-1 confirmation.

**Rationale:** Minimal change — one field addition to the existing creation call. No other crew creation logic needs to change.

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

### D6: Replace `_ensure_crew_running` stop/start with reload-in-place (pending OQ-2)

**Decision:** Once OQ-2 is resolved, replace the stop/start cycle in `_ensure_crew_running` with a call to the reload-in-place endpoint when the container is already running and only a config refresh is needed. Keep stop/start for cold-boot (container stopped or dead).

**Rationale:** Reload-in-place preserves slot identity and avoids the cold-start cost (~0.5s at 0.4.0 vs ~1.3s at 0.3.x). Worth doing while the surrounding code is being touched.

## Migration Plan

1. Pin Containerfiles to `kirocrew:0.4.0`
2. Resolve OQ-1, OQ-2, OQ-3 from the 0.4.0 release notes
3. Apply D1–D5 in `transport/server.py`
4. Apply D6 if OQ-2 is resolved
5. Integration test: full fleet lifecycle (launch, dispatch, pickup, nuke)
