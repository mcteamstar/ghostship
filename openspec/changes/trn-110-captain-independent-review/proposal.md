## Why

The captain tool can drive a full OpenSpec SDD lifecycle via the built-in `sdd` template, but there is no built-in way to run a multi-angle, independent codebase review without writing a custom standing order from scratch. Adding an `independent-review` template gives the Admiral a single, reusable command that dispatches four concurrent reviewers (docs, security, code quality, test coverage), collects their reports, and produces a consolidated findings document — closing a gap that would otherwise require bespoke prompt engineering every time a review is needed.

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

**Usage:**
```
captain(crew_id="trn-review", action="order", template="independent-review")
captain(crew_id="trn-review", action="order", template="independent-review", change_name="trn-107")
```

## Capabilities

### New Capabilities

- `captain/independent-review`: The `independent-review` built-in captain template — its dispatch pattern, the four reviewer roles and their report contracts, the consolidation step, and the `change_name` optional-scoping behavior — is a new spec-level surface of the captain tool.

### Modified Capabilities

(none)

## Impact

- `academy/orders/independent-review.md` — new file (the entire deliverable)
- `transport/captain.py` — no changes required; `_resolve_order_template()` loads it automatically
- `openspec/specs/captain/` — delta spec adds the new `independent-review` template requirement
