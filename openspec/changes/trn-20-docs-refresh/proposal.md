## Why

The ghostship docs have grown organically through TRN-1 to TRN-18. Each change
added or updated docs in its own scope, but no one has reviewed them as a whole.
The result: stale references, missing sections, inconsistent terminology, and
docs that tell different parts of a story that hasn't been stitched together.

This is a stub only — capturing the scope for a future Wraith dispatch.

## What to Review and Update

### README
- SDD lifecycle diagram — verify it matches current behaviour
- Tools table — all 11 tools present and described correctly
- Ghost Academy section — persona descriptions accurate?
- Links to docs — all resolve?
- "Connecting to a harness" section — missing remote deployment pointer
  (deferred from TRN-3)

### docs/architecture.md
- Multiple sections added across TRN-1 through TRN-18 — verify flow and
  coherence, remove any truly stale workarounds that are now fixed
- Operator governance section (TRN-18) — newly added, check accuracy
- Linger section (TRN-3) — verify it reflects the actual install.sh behaviour

### docs/auth.md
- Admiral mail signing, policy signing, API key — all landed separately;
  verify the narrative is coherent end-to-end
- admiral_secret threat model section (TRN-15) — accurate?

### docs/configuration.md
- New env vars from TRN-15 through TRN-19 not yet documented:
  `GA_MIN_FREE_MEM_GB`, `GA_MEMORY_WAIT_SECS`, `GA_SPAWN_MIN_MEMORY_GB`
  (TRN-19 — not yet implemented but worth stubbing)
- `CREW_GATEWAY_PORT`, `GA_FILE_SECRET` — check if documented

### docs/agents.md
- Verify persona descriptions match current raven.json and agent JSONs
  (significant changes in SRV-68, TRN-15)
- Raven lean persona description — current?

### docs/troubleshooting.md (created TRN-3)
- Still only covers Linux install issues; no content for crew launch failures,
  cookie mint failures, OOM issues
- Should cover the `_bootstrap.p` crash (TRN-16) once that's fixed

### docs/remote.md (missing — deferred in TRN-3)
- Full remote deployment playbook: install on remote Linux, API key, TLS,
  public URL config, MCP client registration, known limitations
- Was designed in TRN-3 tasks 5.1–5.7 but not implemented

### academy/steering/STANDING_ORDERS.md
- Verify all mail conventions are current (Maildir, ghostship-mail, HMAC
  signing, verify-admiral-sig)
- Check that the captain mailbox source convention is accurate
- Bounded loop examples — still correct?

## Approach

Dispatch a Wraith to read all docs, identify gaps and stale content, and either
update in place or produce a prioritised list of changes for Ghost to implement.
`docs/remote.md` is the largest missing piece and may warrant its own task.

## Impact

- `docs/` — multiple files updated or created
- `README.md` — minor updates
- `academy/steering/STANDING_ORDERS.md` — possible updates
- No code changes
