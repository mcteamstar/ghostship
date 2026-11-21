## Context

`test_batch.py` and `test_steer.py` patch the Transport TaskService singleton. The stateful test in `test_batch.py` already demonstrates how to build an isolated service. `test_tools.py` checks dispatch errors through the MCP adapter, and the slot resolver tests still live in `test_lifecycle.py`.

## Goals / Non-Goals

Give each task-operation test its own service state and consolidate assertions for the same outcome. Preserve distinct behavior coverage. Production code, launcher and login tests, gateway integration tests, and live E2E scenarios are outside the rewrite.

## Decisions

- Reuse the stateful test's injected collaborators when building a small test fixture. Keep the fake gateway's response and call sequence explicit. Use an in-memory batch registry and mail counts where needed. Preserve existing registry persistence checks that exercise real registry code.
- Drive batch cases through the service entry points. Assert the response, accepted IDs, registry writes, and gateway calls together. Keep distinct cases for full acceptance, refusal before any acceptance, partial acceptance, lost members, timeout, Admiral-mail wakeup, and timestamp expiry. Keep timing deterministic with a controlled clock or patched polling time.
- Exercise steer outcomes directly on the service. Parameterize only cases with the same setup and assertions. Preserve the distinct write sequences for interrupt, queued follow-up, continuation, and stop/resume, including refusals and failed resumes.
- Move slot-routing tests beside task tests. Keep focused MCP tests for schema, argument forwarding, and error compatibility. Verify the production adapters and compatibility exports share one service instance without patching that instance's collaborators in operation tests.

## Risks / Trade-offs

Consolidation can hide the edge cases that gave separate tests value. Preserve externally observable results and gateway side-effect assertions even when fewer test cases cover them.
