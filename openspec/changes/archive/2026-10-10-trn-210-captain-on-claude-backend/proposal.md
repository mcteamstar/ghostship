# Proposal

Source: independent review of `release/0.6.0` at `ee0b3b8` (2026-10-09), run on the Claude backend. Reviewers: **S** security, **Q** quality, **T** test coverage, **D** docs. "Reproduced" means the reviewer or a live check ran code to confirm it; everything else is from reading the code and needs confirming during assessment. Target: a release after 0.6.0.

Full reviewer reports: crew `ghostship-indy-060` tasks `169e9101b28e91e4` (security), `d615d73e3b7c9e37` (quality), `408dea89af5f6789` (test coverage), `45df3b672a262c4c` (docs) — retrieve with `pickup(task_id, crew_id)` while the crew exists. Line numbers refer to `ee0b3b8` and may drift. Next step for whoever picks this up: work through **Assess first**, then write specs, design and tasks with `openspec instructions <artifact> --change <name>`.

## Why

Captain autopilot cannot run on the Claude backend, which ships for the first time in 0.6.0. The indy template's first check-in wrote intent markers and then escalated "review dispatch refused", because Raven declined to read the crew gateway's IPC secret (`.local_secret`) that the dispatch protocol requires. The same review ran fine when dispatched through the transport.

Not the same as TRN-206. That change adds the missing `X-Session-Key` instruction for free-form Captain orders, which otherwise get `member_identity_unavailable` (409). The indy template already told Raven to send that header. On Claude, Raven stopped earlier: it declined to read `.local_secret` at all, so no spawn request was made. TRN-206 does not change that.

## Findings

| Severity | Finding | Where | Who | Status |
|---|---|---|---|---|
| High | Raven on Claude refuses to read `/home/kirocrew/.kiro/crew/.local_secret` ("My instructions bar me from reading credential files directly"), so `POST /api/spawn` with `X-Internal-Secret` never happens. Affects every Captain template (sdd, indy). | `academy/agents/raven.json`; `captain.py:53`; orders templates | live | Reproduced |
| Medium | Raven's replies suggest the ghostship persona prompt may not reach the Claude session: it mentioned Claude Code's `ListAgents` tool and didn't know mailboxes are files under `/var/mail`, which its persona prompt spells out. | KiroCrew claude backend | live | Unconfirmed |
| Low | Three Banshee tasks dispatched to one `banshee` slot ran one after another for the first task, then concurrently. | dispatch slots | live | Observed |

## Assess first

- Confirm whether persona prompts are applied on the Claude backend (KiroCrew 0.8.0 `claude-agent-acp` path).
- Check whether `kirocrew spawn` on 0.8.0 can dispatch a named persona, which would remove the need for the agent to handle the secret at all.

## What Changes

- Prefer a dispatch path that doesn't put a credential in the agent's hands: the `kirocrew` CLI if it supports named persona dispatch, or a transport-side dispatch the Captain calls.
- If persona prompts aren't applied on Claude, fix that delivery first.
- Until fixed, document the limitation and steer Claude users to manual relay.

## Capabilities

### New Capabilities

- None expected.

### Modified Capabilities

- `captain`, `captain/independent-review`, `autonomous-orchestration`, `crew-orchestration/dispatch-coordination`.

## Impact

`academy/agents/raven.json`, `academy/orders/*`, `transport/captain.py`, possibly KiroCrew upstream.
