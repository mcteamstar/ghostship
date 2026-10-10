# Design: TRN-210 — Captain Autopilot on the Claude Backend

## Context

TRN-214 shipped (2026-10-10) and resolved the root blocker: Raven now runs in a member
slot (`dashboard:member-raven`) and uses cookie-only auth for all spawn calls, with the
internal cookie minted inside the container and written to `.dashboard_cookie`. The
`_RAVEN_GATEWAY_ORIENTATION` constant in `captain.py` already reflects this (cookie-only,
no `X-Internal-Secret`, no `X-Session-Key`).

**What remains broken:**

1. **`raven.json` prompt diverges from `captain.py` orientation.** The agent persona
   file at `academy/agents/raven.json` still instructs Raven to read `.local_secret`
   and send `X-Internal-Secret` + `X-Session-Key`. On the Claude backend this causes
   Raven to refuse ("My instructions bar me from reading credential files directly") or
   send the wrong auth headers, breaking every spawn call it attempts. The `captain.py`
   orientation is injected per-checkin as task text — it overrides the persona prompt in
   practice — but the persona prompt is what the Claude session sees at initialisation,
   and on Claude the persona system prompt is delivered first. A Claude session that
   reads its persona prompt and rejects credential-reading before the task text arrives
   is broken.

2. **Persona prompt delivery on Claude is unconfirmed.** The proposal's Medium finding
   ("persona prompt may not reach the Claude session") was unconfirmed as of the original
   report. With TRN-214 architecture (dispatch+steer, member slot), the persona prompt
   from `raven.json` is delivered by KiroCrew's `claude-agent-acp` backend to the Claude
   session at spawn time. Whether Claude honours the full system prompt or truncates /
   ignores it is still unverified against 0.8.0 with the new dispatch path.

3. **`raven.json` model field is `gpt-5.6-luna`.** Raven's persona file specifies a GPT
   model. When the Captain is created on a Claude-backend crew, the dispatch call in
   `_dispatch_captain_checkin` may pass `model` from the Captain order, overriding this
   — but only if the operator explicitly supplies a model. Without an explicit override,
   the gateway may reject the spawn (unknown model) or fall back to the crew's default,
   which may itself be Claude. This needs to be deterministic.

**What does NOT need to change (already handled by TRN-214):**

- `_RAVEN_GATEWAY_ORIENTATION` — already cookie-only, correct.
- `_CAPTAIN_CHECKIN_TASK` — already correct.
- `_dispatch_captain_checkin` / `_steer_captain_checkin` — already use member slot,
  already refresh `.dashboard_cookie`. No changes needed.
- `.dashboard_cookie` minting and refresh — done by TRN-214.
- Cookie-only auth protocol — confirmed working by TRN-214 integration tests.

## Goals / Non-Goals

**Goals:**
- `raven.json` prompt reflects cookie-only auth (no `.local_secret`, no
  `X-Internal-Secret`, no `X-Session-Key`). The persona prompt and task text agree.
- Persona prompt delivery on Claude is verified or explicitly documented if
  unverifiable from code alone.
- Captain dispatch on a Claude-backend crew is deterministic re: model selection —
  no silent fallback.

**Non-Goals:**
- Fixing the concurrently-running Banshee slot observation (proposal Low finding) —
  out of scope, separate issue.
- Adding Claude-specific tooling or permissions — Raven's tool list is unchanged.
- Modifying the cookie minting or refresh path — owned by TRN-214.
- Changing the Captain dispatch architecture — `dispatch+steer` stays.

## Decisions

**D1: Fix `raven.json` prompt to use cookie-only auth.**

The `raven.json` prompt is the canonical source of Raven's standing instructions on how
to spawn. The `_RAVEN_GATEWAY_ORIENTATION` constant serves the per-checkin task text,
which is good — but the persona prompt is what Raven reads at session start, and it must
not contradict the task text. The fix: replace the `.local_secret` / `X-Internal-Secret`
/ `X-Session-Key` instructions in `raven.json` with the cookie-only pattern matching
`_RAVEN_GATEWAY_ORIENTATION`.

The two places must stay in sync. To enforce that, `_RAVEN_GATEWAY_ORIENTATION` is the
single canonical text for spawn auth instructions. The `raven.json` prompt is updated to
match the current `_RAVEN_GATEWAY_ORIENTATION` wording exactly for the auth paragraph,
so a reviewer can confirm they are consistent by inspection.

**D2: Verify persona prompt delivery via `claude-agent-acp` spawn path.**

The KiroCrew 0.8.0 `claude-agent-acp` dispatch path passes agent files to the Claude
Code session. Verification is done by inspecting `lifecycle.py` and any `claude-agent-acp`
configuration for how agent JSON is forwarded. If a code-level confirmation is not
possible (KiroCrew internals are closed source), document the finding in this design and
add an integration test assertion that verifies Raven's response on the first check-in
references mailboxes (not `ListAgents`).

**D3: Make model selection deterministic for Claude-backend Captain crews.**

`_dispatch_captain_checkin` already accepts a `model` parameter forwarded from the
Captain order. When the crew uses a Claude backend (crew `acp_backend == "claude"`), the
transport should default the Captain dispatch model to the crew's configured model rather
than relying on `raven.json`'s `"model"` field, which is GPT-specific. Two options:

- **(chosen)** When `model` is None in `_dispatch_captain_checkin`, read the crew's
  default model from the registry and pass it explicitly. This ensures Claude-backend
  crews always dispatch Raven on a compatible model without operator override.
- Alternatively, set `raven.json` model to a sentinel that means "use crew default". Not
  chosen — `raven.json` is also used on non-Claude crews, so changing the model field
  would break those.

**D4: No new `raven.json` tool permissions needed.**

Raven already has `["read", "grep", "glob", "shell"]`. Shell is sufficient for `cat`,
`curl`, and `kirocrew` CLI calls. No additions required.

## Architecture

```
On a Claude-backend crew, Captain check-in lifecycle:

  Captain cron → _dispatch_captain_checkin()
      │
      ├── reads internal_cookie from registry
      ├── writes .dashboard_cookie inside container
      ├── POST /api/spawn  {agent: "raven", parent_session: "dashboard:member-raven",
      │                     task: _CAPTAIN_CHECKIN_TASK,
      │                     model: <crew_default_model>}   ← D3: explicit model
      │
  KiroCrew gateway → claude-agent-acp backend
      │
      ├── delivers raven.json persona prompt to Claude session  ← D2: verified
      ├── delivers _CAPTAIN_CHECKIN_TASK as task text
      │
  Raven (Claude) reads persona prompt:
      │   "...authenticate with Cookie: mc_token_5476=..."    ← D1: fixed
      │
  Raven reads .dashboard_cookie, spawns with cookie auth
      └── POST /api/spawn {Cookie: mc_token_5476=...}  → 200 spawned
```

## Risks / Trade-offs

**[Risk] `raven.json` and `_RAVEN_GATEWAY_ORIENTATION` drift again.**
→ Mitigation: add a unit test that compares the auth-instruction paragraph in
`raven.json` with the `_RAVEN_GATEWAY_ORIENTATION` constant to detect divergence at CI.

**[Risk] Persona prompt delivery on Claude unverifiable from source alone.**
→ Mitigation: integration smoke test (see tasks 3.1–3.2) — Raven's first-cycle response
confirms it knows mail is in `/var/mail`, not `ListAgents`. This is the same signal
the original finding used to detect the problem.

**[Risk] Model defaulting adds a conditional branch to `_dispatch_captain_checkin`.**
→ Mitigation: the branch is simple: if model is None and `acp_backend == "claude"`,
read `model` from the crew's registry entry `"model"` key. No new registry fields.
Existing non-Claude paths are unaffected (model stays None → gateway picks default,
same as today).

## Open Questions

None — all decisions needed for the task breakdown are resolved above.
