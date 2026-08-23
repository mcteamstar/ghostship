## Context

See proposal.md — Why.

The doc corpus is spread across `docs/` (6 files), `README.md`, and
`academy/steering/STANDING_ORDERS.md`. Each file has been touched
independently through TRN-1–TRN-21 with no integrative review pass.
Key gaps as of this writing:

- `docs/configuration.md` — missing `GA_MIN_FREE_MEM_GB`,
  `GA_MEMORY_WAIT_SECS`, `GA_SPAWN_MIN_MEMORY_GB` (TRN-19, not yet
  implemented), `CREW_GATEWAY_PORT` (hardcoded constant, not
  user-settable — needs a note in docs explaining that).
- `docs/remote.md` — does not exist; remote deployment playbook was
  designed in TRN-3 (tasks 5.1–5.7) but never implemented.
- `docs/troubleshooting.md` — only covers Linux install; no coverage for
  crew launch failures, OOM (TRN-19), or the `_bootstrap.p` crash (TRN-16).
- `docs/auth.md` — three separate auth mechanisms (admiral signing, policy
  signing, API key) were added in separate changes; narrative coherence is
  unreviewed.
- `README.md` — the tools table lists 10 tools; the proposal referenced 11,
  suggesting one may be undocumented or was a miscount that needs resolving.
- `academy/steering/STANDING_ORDERS.md` — mail conventions, bounded-loop
  examples, and captain mailbox notes need verifying against current crew
  behaviour.

This is a **docs-only** change — `skip_specs: true` is already set in
`.openspec.yaml`. No code changes are in scope.

## Goals / Non-Goals

**Goals:**
- Identify and close gaps in `docs/configuration.md` (TRN-19 env vars).
- Create `docs/remote.md` with the deployment playbook designed in TRN-3.
- Expand `docs/troubleshooting.md` to cover crew launch failures and OOM.
- Verify and reconcile `docs/auth.md` end-to-end narrative.
- Verify the README tools table count and descriptions.
- Verify `academy/steering/STANDING_ORDERS.md` is accurate.
- Do lightweight passes over `docs/agents.md` and `docs/architecture.md` for
  stale references.

**Non-Goals:**
- Rewriting docs wholesale — the scope is repair and gap-filling, not a
  style overhaul.
- Implementing any code referenced by docs (TRN-19 env vars stub only).
- Changing any agent persona definitions or architecture described in docs
  (those belong to their own TRNs).

## Decisions

**1. Wraith as the executing agent, not Ghost.**

Wraith is the recon/documentation persona and is read-only over code. This
change has no code impact, so Wraith's constraints are the right fit.
Ghost would work mechanically, but using the right persona keeps the
audit trail clean and leaves Ghost free for implementation work.

**2. `docs/remote.md` gets its own task, not a sub-section.**

The remote deployment guide is substantial enough (TLS, API key, reverse
proxy, MCP client registration, known limitations) that embedding it as a
section in another file would make that file too long. A dedicated file
matches the existing docs structure where `docs/configuration.md`,
`docs/auth.md`, etc. are each standalone.

**3. TRN-19 env vars documented as "stub — not yet implemented".**

The three memory-aware spawn vars (`GA_MIN_FREE_MEM_GB`,
`GA_MEMORY_WAIT_SECS`, `GA_SPAWN_MIN_MEMORY_GB`) appear in TRN-19's design
but TRN-19 is not yet applied. The right approach is to add them to
`docs/configuration.md` with an explicit "planned — not yet in this release"
note, so readers aren't surprised if the vars have no effect on the current
build. When TRN-19 lands, the note is removed.

**4. Read-order for the Wraith pass: config → auth → troubleshooting → remote → README → agents → architecture → STANDING_ORDERS.**

Start with the most concrete gaps (missing env vars, missing file) before
doing integrative review. Config and auth are narrow and high-confidence;
architecture and STANDING_ORDERS are broader and checked last when context
is warm.

## Risks / Trade-offs

[Wraith has no write access to code] → Not a risk here; all targets are
`.md` files or plain text. No mitigation needed.

[TRN-19 env vars not yet implemented] → Documenting them with a "planned"
note is the right hedge; if TRN-19 ships before this change is applied, the
note just needs removal. Low risk.

[`docs/remote.md` may reveal architectural gaps] → If Wraith discovers the
TRN-3 remote-deployment design is stale or incomplete, the correct response is
to document what *is* true today and flag the gap for a future TRN, not to
improvise new architecture in a docs change.

[README tool count discrepancy (10 vs. 11)] → The proposal referenced 11
tools; the current table has 10. Wraith should count carefully and either
identify the missing tool or correct the proposal's reference count. If a
tool is genuinely undocumented, that warrants an addition; if the count was
wrong, no change beyond the table is needed.

## Migration Plan

No deployment steps — this is a docs-only change. Apply via Wraith
dispatched to a crew with `repo/` checked out. Changes take effect when
the updated files are committed and pushed; no restart required.

## Open Questions

None — the scope is well-bounded and all key decisions above are resolved.
