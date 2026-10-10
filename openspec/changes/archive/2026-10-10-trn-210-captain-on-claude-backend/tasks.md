# Tasks: TRN-210 — Captain Autopilot on the Claude Backend

## 1. Fix `raven.json` spawn-auth instructions

- [x] 1.1 In `academy/agents/raven.json`, replace the auth paragraph that reads
  `.local_secret` / `X-Internal-Secret` / `X-Session-Key` with the cookie-only pattern:
  read `.dashboard_cookie` inline, send `Cookie: mc_token_5476=<value>` and
  `Origin: ...` on all spawn REST calls. The new wording must match
  `_RAVEN_GATEWAY_ORIENTATION` in `transport/captain.py` exactly for the auth section.
- [x] 1.2 Remove the "Read the secret file only inline, right when you need it" sentence
  and any reference to `KIRO_SESSION_ID` or `X-Session-Key` from the prompt.
  (The verbatim `_RAVEN_GATEWAY_ORIENTATION` text — required for exact match by 1.1 —
  retains the negative instruction "Do NOT send X-Internal-Secret or X-Session-Key";
  the stale credential-reading sentence and bare `$KIRO_SESSION_ID` reference are gone.)
- [x] 1.3 Preserve all other prompt content unchanged (mailbox skimming instructions,
  dispatch deduplication checklist, response format rules).

## 2. Make Captain dispatch model deterministic on Claude-backend crews

- [x] 2.1 In `transport/server.py`, in `_dispatch_captain_checkin`: when `model` is
  `None` and the crew's registry entry has `acp_backend == "claude"` (or the crew's
  configured model is a Claude model string), read the crew's `"model"` value from the
  registry and pass it as `spawn_body["model"]`. This ensures Claude-backend Raven is
  always dispatched on a compatible model without requiring an operator override.
- [x] 2.2 Apply the same defaulting in `_steer_captain_checkin`'s fallback dispatch
  path (the `conversation_gone` recovery path calls `_dispatch_captain_checkin`
  directly, so the fix in 2.1 covers it — verify no separate patch needed).
  VERIFIED: `_steer_captain_checkin` recovers via `_dispatch_captain_checkin(crew,
  crew_id, model=effective_model)`; when `effective_model` is None the 2.1 defaulting
  applies. No separate patch needed.
- [x] 2.3 Add a unit test: `_dispatch_captain_checkin` on a crew with
  `acp_backend="claude"` and `model="claude-sonnet-4-5"` passes `model` in the spawn
  body even when the caller passes `model=None`.
  (`CaptainClaudeModelDefaultingTests` in `tests/unit/test_captain.py`.)

## 3. Verify persona prompt delivery on Claude

- [x] 3.1 Inspect the KiroCrew 0.8.0 spawn path for `claude-agent-acp` (check
  `transport/lifecycle.py` and any agent-acp config) to confirm `raven.json` prompt is
  delivered to the Claude session. Document the finding as a comment in this tasks file
  or in design.md.
  (Documented in design.md "Persona Prompt Delivery — source finding": `_copy_agents`
  copies `raven.json` into the crew container backend-agnostically; the gateway's
  closed-source `claude-agent-acp` system-prompt handoff is covered by the 3.2 smoke
  test.)
- [x] 3.2 If the delivery path cannot be confirmed from source (closed-source KiroCrew
  internals), add an integration smoke-test note in `design.md` under Risks: on first
  Claude-backend Captain check-in, Raven's response should reference `/var/mail/` paths
  (confirming persona prompt was received), not `ListAgents` tool usage.
  (Added as the "Smoke-test note (task 3.2)" under Risks in design.md.)

## 4. Add a divergence-detection unit test

- [x] 4.1 In the transport test suite, add a test that reads `raven.json` and asserts
  the prompt does not contain the strings `".local_secret"`, `"X-Internal-Secret"`, or
  `"X-Session-Key"`. This catches future regressions where the persona file diverges
  from `_RAVEN_GATEWAY_ORIENTATION`.
  (`RavenPersonaAuthDivergenceTests.test_raven_prompt_has_no_internal_secret_auth_artifacts`
  asserts no `.local_secret` and no `X-Internal-Secret: ` / `X-Session-Key: ` HEADER
  usage — the discriminating form, since the canonical orientation text legitimately
  names those headers in its "Do NOT send ..." negative instruction. The verbatim-match
  test `test_raven_prompt_auth_paragraph_matches_orientation_constant` is the primary
  anti-drift guard.)
- [x] 4.2 Add a test that reads `raven.json` and asserts the prompt contains
  `".dashboard_cookie"` — confirming cookie-only auth is present in the persona.
  (`RavenPersonaAuthDivergenceTests.test_raven_prompt_uses_dashboard_cookie`.)

## 5. Validation

- [x] 5.1 Run the full transport unit test suite; confirm all tests pass.
  (`tests/run.sh --unit`: 1230 passed, 1 deselected (slow). The 8 new tests pass.)
- [ ] 5.2 On a Claude-backend crew: trigger a Captain SDD order; confirm Raven dispatches
  Ghost successfully without refusing to read credentials.
  BLOCKED (live-only): requires a running Claude-backend crew + operator infrastructure,
  not available in the isolated SDD worktree. Covered by the 3.2 smoke-test criterion.
- [ ] 5.3 Confirm `.dashboard_cookie` is read (not `.local_secret`) in Raven's shell
  transcript during the Captain check-in.
  BLOCKED (live-only): same as 5.2 — needs a live Claude-backend check-in transcript.
