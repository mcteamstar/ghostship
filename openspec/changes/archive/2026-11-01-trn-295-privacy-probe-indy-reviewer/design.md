# Design

## Context

The `independent-review` template (`academy/orders/independent-review.md`)
currently dispatches 4 concurrent agents. Raven drives the cycle: dispatch →
wait for N mail reports → consolidate → mail admiral → self-cancel. Each
reviewer uses a distinct task prefix to allow Raven to track them via the
three-signal dispatch-coordination check.

The test-coverage Banshee is the critical path: it scans the full test suite
alone, while docs/security/quality finish earlier. The privacy gap is a
separate problem — no reviewer currently looks for infrastructure leakage.

See `proposal.md — Why` for motivation.

## Goals / Non-Goals

**Goals:**
- Add privacy Banshee as 5th reviewer in indy, with its own mail subject
- Add `privacy` standalone template that runs the same Banshee independently
- Shard test-coverage across N=3 parallel Banshees to cut indy wall-clock time
- All changes are in Captain order templates and docs — zero transport code changes

**Non-Goals:**
- Automated remediation of privacy findings (report only)
- Dynamic N (shard count is fixed at 3 in the template; a future change can parameterise it)
- Changing how security, quality, or docs reviewers work

## Decisions

### D1 — Privacy reviewer is a Banshee, not a Wraith

Wraith is read-only recon. Privacy scanning involves judgment calls (is this
hostname an example or a real one?) that benefit from Banshee's quality-review
disposition. Wraith is for docs accuracy; privacy is a different concern even
though it touches docs.

### D2 — Test-coverage sharded by directory, not by file count

Three shards covering `transport/`, `tests/unit/`, and `tests/integration/` +
everything else maps naturally onto the codebase structure. Alternative: equal
file-count splits. Rejected — file-count splits cut across module boundaries,
making each shard's findings harder to attribute and act on.

Shard assignments baked into the template (not computed at dispatch time):
- Shard A: `transport/` source files
- Shard B: `tests/unit/`
- Shard C: `tests/integration/` + all other paths

### D3 — Privacy standalone template reuses the same Banshee task, not a separate persona

The privacy Banshee task description is identical whether dispatched by indy or
by the standalone template. The difference is only in who waits for the result:
indy's Raven (which folds it into the consolidated report) vs. the standalone
template's Raven (which forwards directly to admiral@). No new persona needed.

### D4 — Raven waits for all N test-coverage shards before consolidating

Alternative: consolidate as soon as any shard finishes, merge partial results.
Rejected — partial consolidation adds complexity with minimal benefit; the
shards are parallel so the wait is bounded by the slowest shard, not all three.

### D5 — N=3 shards hardcoded in the template

Parameterising N adds complexity (Raven needs to know N to know when it's
done). Fixed at 3 for now; a future change can introduce a `test_coverage_shards`
parameter to the template if needed.

## Risks / Trade-offs

- **Shard imbalance** — `transport/` is much larger than `tests/integration/`.
  Shard C may finish significantly faster than Shard A.
  Mitigation: acceptable for now; rebalancing is a one-line template edit.

- **Memory pressure with 7 concurrent agents** — indy now dispatches 7 agents
  at once (Wraith + 3×Banshee quality/security/privacy + 3×Banshee test shards).
  The existing memory-pressure backoff in the template handles this: refused
  spawns are retried on the next check-in.
  Mitigation: document expected concurrency in architecture.md.

- **Privacy false positives** — the Banshee may flag hostnames used as
  examples (e.g. `example.com`, `localhost`) or placeholder IPs. 
  Mitigation: the task description explicitly excludes RFC-standard example
  domains and loopback addresses from the scan scope.

## Migration Plan

1. Update `academy/orders/independent-review.md` — add privacy reviewer + test-coverage sharding
2. Add `academy/orders/privacy.md` standalone template
3. Update skill and docs
4. No transport restart needed — order templates are read at Captain dispatch time from the mounted `orders/` volume

Rollback: revert the template files. No registry or DB migration.
