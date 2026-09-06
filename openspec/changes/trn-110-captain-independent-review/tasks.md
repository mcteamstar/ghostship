## 1. Create the change-scoped template

- [ ] 1.1 Create `academy/orders/independent-review.md` with YAML front-matter (`description: "Dispatch four concurrent independent reviewers scoped to a named change and consolidate their findings."`) and a body that opens with `Scope: change <change>` as its first non-empty line so `_resolve_order_template()` substitutes the change name
- [ ] 1.2 Write the Raven standing-order prose for the dispatch phase: on the first check-in, dispatch four reviewers concurrently — Wraith for docs completeness, and three Banshee instances for security, code quality, and test coverage — each via an authenticated `/api/spawn` call preceded by a per-reviewer intent marker in `raven@localhost`
- [ ] 1.3 Write distinct task description prefixes for each Banshee dispatch (`REVIEW security <intent_id>`, `REVIEW quality <intent_id>`, `REVIEW test-coverage <intent_id>`) so Raven can track three concurrent Banshee tasks without false-positive duplicate detection
- [ ] 1.4 Write the reviewer context block for each of the four tracks, specifying what each reviewer analyses and that it must mail a standalone self-contained report to `raven@localhost` when done, scoped to the named change
- [ ] 1.5 Write the wait-and-collect prose: on subsequent check-in cycles Raven reads `raven@localhost` for incoming reviewer reports; it SHALL NOT send the consolidated document until all four reports are present
- [ ] 1.6 Write the consolidation prose: once all four reports are present, Raven produces a single findings document grouped by severity (Critical / High / Medium / Low / Informational), cross-references findings flagged by more than one reviewer, adds recommended next actions, and mails the document to `admiral@localhost`
- [ ] 1.7 Include `{{RAVEN_GATEWAY_ORIENTATION}}`, `{{RAVEN_STORE_RESOLUTION}}`, and `{{RAVEN_SELF_CANCEL}}` placeholders in the body at the appropriate points, following the same pattern as `academy/orders/sdd.md`

## 2. Create the whole-codebase template variant

- [ ] 2.1 Create `academy/orders/independent-review-all.md` — identical to the change-scoped template except the first line reads `Scope: entire codebase` (no `<change>` token) and the reviewer context blocks instruct each reviewer to examine the full codebase with no change-specific restriction
- [ ] 2.2 Update the YAML front-matter `description` field to read `"Dispatch four concurrent independent reviewers across the entire codebase and consolidate their findings."`

## 3. Validate and test template loading

- [ ] 3.1 Confirm `_resolve_order_template("independent-review", change_name="trn-107")` returns a body with `Scope: change trn-107` and all three `{{RAVEN_*}}` placeholders substituted (no residual `{{...}}` tokens)
- [ ] 3.2 Confirm `_resolve_order_template("independent-review", change_name=None)` raises `ValueError` (body contains `<change>` but no `change_name` given)
- [ ] 3.3 Confirm `_resolve_order_template("independent-review-all", change_name=None)` returns a body with `Scope: entire codebase` and no residual `{{...}}` tokens
- [ ] 3.4 Run `tests/run.sh --unit` — all existing tests pass with no regressions

## 4. Documentation

- [ ] 4.1 Add the `independent-review`, `independent-review-all`, and `sdd-parallel` templates to the `captain` tool's docstring examples in `transport/server.py` so the MCP tool description surfaces all invocation forms to agent callers

## 5. `sdd-parallel` order template

- [ ] 5.1 Create `academy/orders/sdd-parallel.md` with YAML front-matter (`description: "Drive multiple named OpenSpec changes concurrently through the standard SDD lifecycle."`) and a `<changes>` token (comma-separated change names, e.g. `trn-110,trn-115`) as the first substitution
- [ ] 5.2 Write the opening orientation block: Raven parses `<changes>` into a list of individual change names on first receipt and maintains a per-change state table (change name → current phase, last dispatched persona, pending intent IDs) in its working notes
- [ ] 5.3 Write the per-change lifecycle prose — for each change independently, Raven applies the same Spectre → Ghost → Banshee → Reaper dispatch-coordination logic as the `sdd` template; all intent markers and task description prefixes use the existing `SDD dispatch <intent_id> <change> <persona>` format so cross-change collision cannot occur
- [ ] 5.4 Write the independent progress clause: a change that reaches archive does not block or affect other changes still in progress; Raven sends a per-change completion mail to `admiral@localhost` when each individual change finishes
- [ ] 5.5 Write the final summary clause: when all changes are done, Raven sends a summary mail to `admiral@localhost` listing each change and its outcome, then self-cancels the captain job
- [ ] 5.6 Include `{{RAVEN_GATEWAY_ORIENTATION}}`, `{{RAVEN_STORE_RESOLUTION}}`, and `{{RAVEN_SELF_CANCEL}}` placeholders at the appropriate points

## 6. `transport/captain.py` — `<changes>` token support

- [ ] 6.1 In `_resolve_order_template()`, add a branch: after the existing `<change>` substitution block, check if the body contains `<changes>`; if so, validate that `change_name` is not None and not empty, split on comma, strip whitespace, call `_validate_captain_change_name` on each element, and substitute `<changes>` with the original `change_name` string (the template body receives the raw comma-separated value as-is)
- [ ] 6.2 Ensure `<change>` and `<changes>` are mutually exclusive in a template body — if both are present, raise `ValueError("Template body must not contain both <change> and <changes>")`
- [ ] 6.3 Add unit tests in `tests/unit/test_captain.py`:
  - `test_resolve_sdd_parallel_substitutes_changes` — call `_resolve_order_template("sdd-parallel", change_name="trn-110,trn-115")`, assert `<changes>` is replaced and `<change>` is absent
  - `test_resolve_sdd_parallel_validates_each_name` — pass an invalid individual name (e.g. `"trn-110,bad name!"`) and assert `ValueError` is raised
  - `test_resolve_sdd_parallel_requires_change_name` — call with `change_name=None` and assert `ValueError`
  - `test_resolve_template_rejects_both_tokens` — create a synthetic template body containing both `<change>` and `<changes>` and assert `ValueError`
