## Why

The captain tool can drive a full OpenSpec SDD lifecycle via the built-in `sdd` template, but there is no built-in way to run a multi-angle, independent codebase review without writing a custom standing order from scratch. Adding an `independent-review` template gives the Admiral a single, reusable command that dispatches four concurrent reviewers (docs, security, code quality, test coverage), collects their reports, and produces a consolidated findings document — closing a gap that would otherwise require bespoke prompt engineering every time a review is needed.

Additionally, the `sdd` template is single-change only. Each invocation substitutes one `<change>` token, and its dispatch-coordination logic keys on `<change>` + `<persona>` in task descriptions. Running two `sdd` captains for different changes therefore requires two separate crews. A new `sdd-parallel` template lifts this restriction, letting Raven drive N changes concurrently within a single crew by namespacing all intent markers and dispatch-coordination checks by change name.

## What Changes

**New academy order template (`academy/orders/independent-review.md`):**
- Dispatches four concurrent, isolated reviewer agents — each works directly from the code with no knowledge of the others' findings
- Each reviewer sends its own standalone report to `raven@localhost`
- The captain reads all four reports and produces a single consolidated findings document sent to `admiral@localhost`
- Template accepts an optional `<change>` placeholder; when provided, reviewers scope their analysis to recent changes; without it, they review the whole codebase
- Template follows the same YAML front-matter + `{{PLACEHOLDER}}` substitution pattern as `academy/orders/sdd.md`

**No changes to `transport/captain.py`** — `_resolve_order_template()` already loads any file under `academy/orders/<name>.md`; the new template is picked up automatically.

**Four independent review tracks:**
1. **Docs completeness (Wraith)** — docs accuracy against codebase, stale references, missing env vars
2. **Security review (Banshee)** — threat model, known vuln classes, secret handling, injection surfaces
3. **Code quality (Banshee)** — race conditions, error handling gaps, edge cases in recent changes
4. **Test coverage (Banshee)** — unit test gaps, missing scenarios, e2e gaps

**New academy order template (`academy/orders/sdd-parallel.md`):**
- Drives N OpenSpec changes concurrently within a single crew, using one captain standing order
- Takes a `<changes>` token (comma-separated list of change names, e.g. `trn-110,trn-115`) substituted at order time
- All intent markers, task description prefixes, and dispatch-coordination checks are namespaced by change name (`SDD dispatch <intent_id> <change> <persona>` — same as the existing `sdd` template, so cross-change false-positive matching is naturally prevented)
- Each change progresses through its own independent Spectre → Ghost → Banshee → Reaper lifecycle; a change that finishes does not block others
- The captain reports per-change completion status to `admiral@localhost` as each change completes, and sends a final summary when all changes are done

**`transport/captain.py` — `_resolve_order_template()` extension:**
- The `sdd-parallel` template requires a `<changes>` token (list) rather than the single `<change>` token. `_resolve_order_template()` currently only handles `<change>`. A new substitution path is needed: when the body contains `<changes>`, validate and substitute a comma-separated `change_name` string (the caller passes the full comma-separated list as `change_name`).
- Validation: each individual name in the comma-separated list must pass `_validate_captain_change_name`. No other changes to captain.py.

**Usage:**
```
# Independent review (existing)
captain(crew_id="trn-review", action="order", template="independent-review", change_name="trn-107")
captain(crew_id="trn-review", action="order", template="independent-review-all")

# Parallel SDD — two changes in one crew
captain(crew_id="trn-impl", action="order", template="sdd-parallel", change_name="trn-110,trn-115")
```

## Capabilities

### New Capabilities

- `captain/independent-review`: The `independent-review` built-in captain template — its dispatch pattern, the four reviewer roles and their report contracts, the consolidation step, and the `change_name` optional-scoping behavior.
- `captain/sdd-parallel`: The `sdd-parallel` built-in captain template — multi-change concurrent SDD lifecycle, per-change namespace isolation in dispatch coordination, and the `<changes>` token substitution contract.

### Modified Capabilities

- `captain`: `_resolve_order_template()` gains `<changes>` token substitution alongside the existing `<change>` substitution.

## Impact

- `academy/orders/independent-review.md` — new file
- `academy/orders/independent-review-all.md` — new file
- `academy/orders/sdd-parallel.md` — new file
- `transport/captain.py` — `_resolve_order_template()`: add `<changes>` token handling and per-name validation
- `tests/unit/test_captain.py` — tests for `<changes>` substitution, validation, and `sdd-parallel` template loading
- `openspec/specs/captain/` — delta spec covers both new templates and the `_resolve_order_template()` extension
