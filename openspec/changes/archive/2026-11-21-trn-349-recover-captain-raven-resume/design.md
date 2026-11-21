## Context

Captain persists the ID returned by `/continue` before that task finishes. The observed restore error appeared in the failed task outcome, while Captain's schedule still showed enabled. Existing synchronous handling alone cannot detect that sequence.

## Decisions

- Inspect the tracked Raven task before continuing it on a scheduled check-in. Recognize the terminal failed outcome and explicit `resume_failed` marker. Also recognize the same failure in a structured immediate continuation error if the gateway supplies it. Keep legacy missing and busy paths separate. Do not infer a restore failure from a timeout, bare HTTP status, stale status read, or generic failure.
- Reuse Captain's schedule coordination and admission controls. Clear only the matching failed task ID on the same enabled schedule. If it changed or was stopped, abandon recovery for that tick. Persist the accepted replacement ID through the normal path. If admission defers the spawn, keep the failed ID cleared and let the schedule retry. Treat uncertain spawn acceptance as unresolved until reconciled.
- Start Raven with the standing order and recovery instructions to reconstruct progress from durable records, including pending and confirmed intents and existing task outcomes. Reuse each order's reconciliation rules; hold work with ambiguous evidence. No dependency on a failed session transcript or a specific order template.

## Risks

A false positive can start a second coordinator. Require explicit evidence and verify schedule ownership before recovery. A fresh session can lose in-memory progress, so durable reconciliation must precede further dispatch.
