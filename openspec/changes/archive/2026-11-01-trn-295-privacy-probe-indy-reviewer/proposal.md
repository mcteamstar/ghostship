# Proposal

## Why

Ghostship is open source. Any internal infrastructure reference baked into a
comment, spec, doc, or config example — hostnames, Tailscale IPs, VM names,
internal ticket IDs, real file paths, real names — is permanently public once
pushed. The existing indy review has four Banshee/Wraith reviewers covering
security, quality, test coverage, and docs, but nothing that specifically scans
for this class of leakage. It surfaces as a manual `chore: scrub internal
hostnames` commit after the fact rather than being caught systematically.

## What Changes

- **`academy/orders/independent-review.md`** — two changes:
  1. Add a 5th concurrent reviewer: a Banshee dispatched with task prefix
     `REVIEW privacy <intent_id> <change?>`, waiting for subject
     `review privacy done <change?>`, folded into the consolidated report
     under a **Privacy** section.
  2. Fan out the test-coverage reviewer across N parallel Banshees (default
     N=3) each covering a disjoint shard of the codebase. Test coverage is
     currently the critical path for indy wall-clock time; sharding cuts it
     proportionally. Raven collects all N sub-reports before consolidating.

- **`academy/orders/privacy.md`** — new standalone Captain order template
  (aliases: `privacy-probe`, `scrub`). Dispatches the same Banshee privacy
  task against the whole codebase, mails the report directly to
  `admiral@localhost` with subject `privacy probe complete`, then self-cancels.

- **Banshee privacy review task** — scans source code, docs/, openspec/ (specs,
  changes, proposals, tasks) for:
  - Hostnames and FQDNs (internal or operator-specific)
  - IP addresses (RFC-1918: 10.x, 192.168.x, 172.16-31.x; Tailscale: 100.x)
  - Internal VM/service names used as identifiers in non-example contexts
  - Ticket references that are internal (e.g. `TRN-nnn` in source comments)
  - Real file paths (e.g. `/Users/<name>/`, `~/development/`)
  - Real names or email addresses outside of git authorship context
  - Internal URLs baked into strings, comments, or config examples
  - Each finding: file, line, category, quoted text, recommended action
    (remove / replace with placeholder / move to docs with disclaimer)

- **`ghostship-command/SKILL.md`** — document `privacy` / `privacy-probe` /
  `scrub` as an available Captain template alongside `sdd`, `indy`, `free-will`.

- **`docs/architecture.md`** — add privacy probe to the Captain supervision
  section.

## Capabilities

### New Capabilities

- `captain/privacy-probe`: The privacy probe Captain template — standalone
  dispatch of a privacy Banshee against the whole codebase, producing a
  self-contained findings report mailed to the Admiral.

### Modified Capabilities

- `captain/independent-review`: The independent review template now dispatches
  5 concurrent reviewers (adding privacy) and waits for 5 reports before
  consolidating.

## Impact

- `academy/orders/independent-review.md` — add 5th reviewer
- `academy/orders/privacy.md` — new file
- `.claude-plugin/skills/ghostship-command/SKILL.md` — document new template
- `docs/architecture.md` — Captain supervision section
