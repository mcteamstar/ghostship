## Context

See proposal.md — Why. The captain tool resolves order templates by reading `academy/orders/<name>.md` via `_load_order_template()` and substituting `{{PLACEHOLDER}}` tokens and the optional `<change>` literal via `_resolve_order_template()`. The `sdd` template demonstrates the full pattern: YAML front-matter with a `description` field, a prose body, and Raven-driven lifecycle logic delivered as a standing mail order.

The four reviewer tracks in this change create a coordination challenge absent from `sdd`: Raven must dispatch all four concurrently, then collect four separate mail reports before consolidating. The SDD template drives one persona at a time in sequence; this template drives four in parallel and then waits for all four to report back.

Relevant files:
- `academy/orders/sdd.md` — reference template (structure, placeholder substitution, front-matter)
- `transport/captain.py` — `_load_order_template()`, `_resolve_order_template()`, `_substitute_placeholders()`

## Goals / Non-Goals

**Goals:**
- Define the standing-order prose Raven receives when the template is invoked — dispatch wording, report contracts, consolidation logic, and change-scoping variants
- Keep the implementation to new files under `academy/orders/`; no changes to `transport/captain.py`

**Non-Goals:**
- Implementing Raven's per-check-in reasoning in Python — the template is natural-language instructions delivered as mail
- Adding a new placeholder constant to `transport/captain.py`

## Decisions

### Decision: Single Raven session drives all four reviewers

Raven dispatches all four reviewers in one check-in cycle using four separate authenticated `/api/spawn` calls, each preceded by a per-persona intent marker in `raven@localhost`. On subsequent check-in cycles, Raven polls `raven@localhost` for incoming reports and, once all four are present, produces the consolidated document.

Alternative considered: a separate "coordinator" persona Raven dispatches first, which then re-dispatches the four reviewers. Rejected — adds a round-trip with no benefit; Raven can hold four pending intents concurrently.

### Decision: Reviewers report to raven@localhost; Raven consolidates and mails admiral@localhost

Each reviewer mails its standalone findings to `raven@localhost`. Raven reads all four, synthesises them, and mails the consolidated document to `admiral@localhost`. This enables cross-referencing, severity grouping, and a single coherent output. Reviewers mailing directly to `admiral@localhost` was rejected — the Admiral would receive four uncoordinated partial reports.

### Decision: Two template files to handle optional change_name

`_resolve_order_template()` raises `ValueError` when the body contains the `<change>` literal but no `change_name` is given. To make scoping truly optional, two template files are provided:

- `academy/orders/independent-review.md` — contains `<change>` in a preamble line; requires `change_name`. Used when scoping to a specific change.
- `academy/orders/independent-review-all.md` — identical body but with the preamble line replaced by `"Scope: entire codebase"` and no `<change>` token. Used for whole-codebase review.

Usage:
```
captain(crew_id="trn-review", action="order", template="independent-review-all")
captain(crew_id="trn-review", action="order", template="independent-review", change_name="trn-107")
```

Alternative considered: a single template with conditional prose for Raven to parse. Rejected — relies on Raven parsing its own rendered mail subject for a scope signal, which is fragile. Alternative considered: a new `{{CHANGE_SCOPE}}` placeholder in `captain.py`. Rejected — requires modifying captain.py, which is out of scope.

### Decision: Three concurrent Banshee dispatches differentiated by task description prefix

Three of the four reviewers are Banshee instances. The dispatch-coordination guard checks the `agent` field and task description. To let Raven track three concurrent Banshee tasks without false-positive duplicate detection, each Banshee dispatch uses a unique, descriptive task description prefix: `REVIEW security <intent_id>`, `REVIEW quality <intent_id>`, `REVIEW test-coverage <intent_id>`. Raven checks for these specific prefixes in `kirocrew spawn list` rather than only the `agent: banshee` field.

## Risks / Trade-offs

- **Three concurrent Banshee instances**: Raven's duplicate-dispatch guard is per-persona. Three legitimately distinct Banshee tasks will each show `agent: banshee`. Mitigation: unique task description prefixes (see above) let Raven differentiate them; the template explicitly documents the required prefix format.

- **Raven context pressure from four large reports**: Reviewers may produce long findings documents. Mitigation: the template instructs each reviewer to open its report with a short structured summary (severity counts, top findings) before the detailed body, and instructs Raven to read summaries first for cross-referencing.

- **No native wait-for-all-four primitive**: Raven polls on each check-in cycle. If reviewers finish at different times, Raven may do several no-op cycles. Accepted: the check-in interval is operator-configured and the wait is bounded by reviewer completion time.

## Migration Plan

Purely additive — two new files under `academy/orders/`. No migration needed. The transport's `_resolve_order_template()` raises `ValueError` for unknown names, so existing `sdd` invocations are unaffected.

Deploy: merge the PR. Templates are available immediately to any crew whose `academy/orders/` bind-mount includes the new files.

## Open Questions

None.
