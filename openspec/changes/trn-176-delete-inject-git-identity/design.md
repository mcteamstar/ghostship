## Context

See proposal.md. `_inject_git_identity` is a two-line empty stub in `lifecycle.py`. It is not called from any production code path. Two unit tests assert it is a no-op and is not invoked from `_finish_crew_setup`.

## Goals / Non-Goals

**Goals:**
- Remove the dead function and its associated comment/test noise

**Non-Goals:**
- Any change to how git identity is actually injected (env= at container creation — unchanged)

## Decisions

**Delete the function outright rather than keeping a stub.** A documented no-op that is never called adds more confusion than it prevents. The comment at the former call site saying "it has been removed" makes no sense if the function still exists. Alternatives considered: (a) keep but add `# type: ignore` — rejected, adds noise without value; (b) keep for hypothetical future callers — rejected, the function has an empty body and would need to be implemented from scratch anyway.

**Delete the two test methods.** They test a negative invariant ("this function is not called and does nothing") which is trivially true for a deleted function. Keeping tests for non-existent code is misleading.

## Risks / Trade-offs

- [No risk] The function has an empty body and is not reachable from any production code path. Deletion cannot break anything.
