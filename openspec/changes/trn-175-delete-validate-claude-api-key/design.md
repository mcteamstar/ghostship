## Context

See proposal.md. `_validate_claude_api_key` has an empty body. `Config.validate()` calls it and is itself documented as a no-op. The stale `server.py` comment creates a false expectation that startup validation enforces credential presence for Claude/Codex backends — it doesn't; that check is lazy and deferred to `launch()`.

## Goals / Non-Goals

**Goals:**
- Remove the dead helper function
- Fix the misleading startup comment so operators understand actual validation behaviour
- Leave `Config.validate()` as a `pass` so any external callers (there are none currently, but the method is public) don't break

**Non-Goals:**
- Adding real startup validation (that is a separate decision; TRN-170 deliberately deferred it to launch time)
- Changing any validation logic

## Decisions

**Reduce `validate()` to `pass` rather than deleting it.** The method is public API on `Config`. Deleting it could break external tooling even though no internal code depends on it. A `pass` body with an updated docstring is the minimal honest change. Alternatives: (a) delete `validate()` entirely — rejected, breaks public API unnecessarily; (b) add real validation — out of scope for a dead-code cleanup.

**Fix the comment, not just the code.** The `server.py` startup comment is the most dangerous artefact — it describes behaviour that hasn't existed since TRN-170. Fixing it is a correctness fix independent of the code cleanup.

## Risks / Trade-offs

- [No risk] `_validate_claude_api_key` had an empty body. Its removal cannot change runtime behaviour.
- [Low risk] Existing tests assert `validate()` does NOT raise — these tests remain valid with a `pass` body and require no changes.
