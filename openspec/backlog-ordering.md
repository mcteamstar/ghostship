# Backlog Ordering — Post-0.6.0 Changes

Prepared by synthesis Spectre, 2026-10-10.  
Source: TRN-206 and TRN-168 currency assessments; proposals and planning artifacts for
TRN-207 through TRN-213; TRN-168 full artifact set.

---

## 1. Obsolete / Closed Changes

### TRN-206 — raven-gateway-orientation-session-key

**Recommendation: CLOSE (archive)**

TRN-206 proposed adding `X-Session-Key: $KIRO_SESSION_ID` to `_RAVEN_GATEWAY_ORIENTATION`
so Raven could authenticate spawn calls. TRN-214 (already shipped) resolved this by a
fundamentally different mechanism: the entire spawn flow now uses cookie-only auth, and
`_RAVEN_GATEWAY_ORIENTATION` already instructs Raven to read `.dashboard_cookie` and
explicitly forbids sending `X-Internal-Secret` or `X-Session-Key` alongside it. The fix
TRN-206 planned would break the working cookie-only flow.

The tasks.md for TRN-206 is partially checked-off (1.1, 1.2, 1.3, 2.1 done); task 2.2
was blocked and eventually confirmed moot. No residual scope remains.

> **Action:** Archive `openspec/changes/trn-206-raven-gateway-orientation-session-key/`.
> No implementation work required.

---

## 2. Ordered Implementation Sequence

Ordering rationale in brief:

- **TRN-208 first**: critical bug (recovery deadlock reproduced), can hang every crew
  silently. No dependencies on other open changes.
- **TRN-211 second**: high/medium severity; secret delivery hardening is self-contained
  and reduces exposure for every subsequent deployment.
- **TRN-209 third**: high severity login-flow bugs (PTY byte loss reproduced; login
  expiry); directly affects all three auth backends and blocks reliable Codex use.
  Shares code surface with TRN-168 credential injection — should land first.
- **TRN-207 fourth**: high severity security hardening (network exposure defaults,
  auth bypasses); needs architectural decision before planning can complete (see Open
  Questions), but once unblocked this becomes urgent. The assessment files for this
  change were not produced — it still needs a Spectre planning pass.
- **TRN-210 fifth**: captain-on-claude is blocked on understanding the Claude backend's
  persona-prompt delivery. Needs assessment and planning. Medium impact today (most
  crews run kiro), but important for broader backend support.
- **TRN-168 sixth**: OpenCode backend support. Apply-ready after a minor tasks.md
  update (see TRN-168 assessment). Feature addition rather than a fix; sequenced after
  stability and security work.
- **TRN-212 seventh**: test coverage gaps. No production code risk; complements all
  the above fixes by adding the test infrastructure that would catch regressions.
- **TRN-213 eighth**: config/install consistency. Low risk, medium polish value;
  correct after the above changes stabilise the config surface.

---

### Position 1 — TRN-208: Crew Lifecycle Resilience

| Field | Value |
|---|---|
| **Change name** | `trn-208-crew-lifecycle-resilience` |
| **Plane priority** | (Urgent — critical bug reproduced in stubbed harness) |
| **Planning status** | ✅ design.md + tasks.md complete — apply-ready |
| **Summary** | Fixes a recovery self-deadlock (non-reentrant lock re-entered during member enrolment), a registry-clobber on I/O error, a reaper TOCTOU that stops recently-active crews, and several related leak/race bugs. |
| **Blocking dependencies** | None |

Seven task groups covering: deadlock fix (D1), registry I/O (D2), reaper re-check (D3),
Podman error semantics (D4), restart race + retry policy + leak cleanup (D5/D6/D7),
integration tests (group 6). Each group is independently mergeable.

---

### Position 2 — TRN-211: Secret Handling Hardening

| Field | Value |
|---|---|
| **Change name** | `trn-211-secret-handling-hardening` |
| **Plane priority** | (High — medium/high severity findings) |
| **Planning status** | ✅ design.md + tasks.md complete — apply-ready |
| **Summary** | Moves `GA_CREW_ANTHROPIC_API_KEY`, `GA_CREW_OPENAI_API_KEY`, and `KIRO_API_KEY` from plaintext compose.yml env vars to Podman secrets (matching the existing `ga-api-key` pattern), and wires `KIRO_API_KEY` through install.sh so the documented headless auth path works. |
| **Blocking dependencies** | None |

Four task groups: install.sh secret creation (1), compose.yml template update (2),
server.py secret-file readers (3), verification (4). Requires re-running install.sh
after deploy.

---

### Position 3 — TRN-209: Login Flow Hardening

| Field | Value |
|---|---|
| **Change name** | `trn-209-login-flow-hardening` |
| **Plane priority** | (High — two findings reproduced) |
| **Planning status** | ⚠️ design.md done; tasks.md missing — needs tasks generation |
| **Summary** | Fixes PTY byte loss on the 101-upgrade boundary (intermittent login URL loss for kiro/Claude/Codex), adds login-expiry sweep for all three backends (kiro/Codex flows never expire today), and tightens the Codex device-code regex to stop matching prose words. |
| **Blocking dependencies** | None structurally; "Assess first" item — run a real Codex login to confirm device-code format before the regex fix lands (proposal and design both flag this). |

Design decisions are fully resolved (D1–D4). Ghost can generate tasks.md directly
from the design.

---

### Position 4 — TRN-207: Network Exposure Defaults

| Field | Value |
|---|---|
| **Change name** | `trn-207-network-exposure-defaults` |
| **Plane priority** | (Urgent/High — three high-severity findings) |
| **Planning status** | ❌ proposal only — needs assessment, design, and tasks |
| **Summary** | Fixes default install exposing MCP control surface without auth on all interfaces (0.0.0.0), a `X-Forwarded-For` rate-limit bypass (client-controlled key), a dashboard `forward_auth` bypass via WebSocket route, Caddy admin API exposure, and cleartext-by-default TLS. |
| **Blocking dependencies** | Architectural decision required — see Open Questions §A |

The proposal's "Assess first" items must be reproduced on a disposable host before
design can proceed. The default-posture decision (loopback bind vs. required API key
vs. explicit insecure flag) drives most of the implementation scope. This is the
highest-impact unplanned change.

---

### Position 5 — TRN-210: Captain on Claude Backend

| Field | Value |
|---|---|
| **Change name** | `trn-210-captain-on-claude-backend` |
| **Plane priority** | (High — reproduced: Raven refuses to read `.local_secret` on Claude) |
| **Planning status** | ❌ proposal only — needs assessment and planning |
| **Summary** | Captain autopilot cannot run on the Claude backend because Raven declines to read `.local_secret` (credential policy refusal), so no `POST /api/spawn` with `X-Internal-Secret` ever fires; affects every captain template (SDD, indy). |
| **Blocking dependencies** | Architectural decision required — see Open Questions §B. TRN-214 (shipped) resolved Raven-on-kiro spawn; the Claude-backend path is a separate unresolved gap. |

The proposal identifies two candidate fixes: use the `kirocrew` CLI for named-persona
dispatch (removes credential from agent's hands), or a transport-side dispatch the
captain calls. Confirming whether KiroCrew 0.8.0 `kirocrew spawn` supports named
persona dispatch is the first assessment step.

---

### Position 6 — TRN-168: OpenCode Backend Support

| Field | Value |
|---|---|
| **Change name** | `trn-168-opencode-backend-support` |
| **Plane priority** | (Medium — new capability, not a regression) |
| **Planning status** | ⚠️ design.md + tasks.md present; minor tasks.md update required before apply-ready |
| **Summary** | Adds `opencode` as a third optional agent backend alongside `claude` and `codex`: toolchain script, backend validation, login/logout routes, credential injection at crew launch, and documentation. |
| **Blocking dependencies** | TRN-209 (login flow hardening) should land first — both touch `lifecycle.py` credential injection and login container patterns; landing TRN-209 before TRN-168 reduces merge conflict risk. |

The TRN-168 currency assessment found two stale spec scenarios that will create
spec/code contradictions after TRN-168 lands, plus one test that needs converting
from negative to positive. **Required tasks.md additions before Ghost implements:**

1. Task 5.4: Update `openspec/specs/installation/spec.md` — replace "opencode rejected"
   scenario (lines 492–493) with "opencode accepted" scenario.
2. Task 5.5: Update `openspec/specs/crew-acp-backend/spec.md` — replace `"opencode"`
   example in the invalid-backend scenario (line 26) with a different placeholder
   (e.g. `"llama"`).
3. Amend task 1.3 note: converting the existing negative test
   (`GA_AGENT_BACKENDS=claude,opencode` rejected → must become accepted) is required,
   not merely additive.

All other gaps identified in the assessment (docs, config.py inert-settings, install.sh
comment) are covered by existing tasks 5.1–5.3; no new tasks required, but the
implementer should be pointed at the specific lines enumerated in the assessment.

---

### Position 7 — TRN-212: Test Coverage Gaps

| Field | Value |
|---|---|
| **Change name** | `trn-212-test-coverage-gaps` |
| **Plane priority** | (Medium — no production code risk) |
| **Planning status** | ❌ proposal only — needs design and tasks |
| **Summary** | Fills critical test coverage gaps: install/uninstall scripts running the real shell under a sandbox (rather than reimplementing them), direct Codex login tests (currently every test patches the poll, hiding the false-completion bug), PTY helper socketpair tests, and branch coverage for transport. |
| **Blocking dependencies** | TRN-209 and TRN-208 should land first — their bugs exposed the gaps; landing fixes before writing tests ensures the tests cover the correct behaviour, not the broken behaviour. CI integration question (run integration tests in CI) needs a decision — see Open Questions §C. |

---

### Position 8 — TRN-213: Config/Install Consistency

| Field | Value |
|---|---|
| **Change name** | `trn-213-config-install-consistency` |
| **Plane priority** | (Medium — medium/low severity, silent operator confusion) |
| **Planning status** | ❌ proposal only — needs design and tasks |
| **Summary** | Fixes settings documented as tunable but silently ignored by install.sh (GA_PREWARM_*, GA_RATE_LIMIT_DASHBOARD_AUTH, GA_FILE_SECRET), host paths mounted nowhere (GA_ORDERS_DIR, TLS cert paths), PORT only setting Caddy's host port, and negative GA_MAX_ACTIVE_CREWS silently disabling the limit. |
| **Blocking dependencies** | TRN-211 (secret handling hardening) should land first — both touch install.sh and compose.yml; sequencing avoids conflicting edits. Several items in TRN-213 overlap docs and config surface that TRN-168 also touches (GA_AGENT_BACKENDS docs); coordinate to avoid doc conflicts. |

---

## 3. Summary Table

| # | Change | Priority | Planning Status | Depends On |
|---|---|---|---|---|
| 1 | TRN-208 crew-lifecycle-resilience | Urgent/Critical | ✅ Apply-ready | — |
| 2 | TRN-211 secret-handling-hardening | High | ✅ Apply-ready | — |
| 3 | TRN-209 login-flow-hardening | High | ⚠️ Needs tasks.md | — |
| 4 | TRN-207 network-exposure-defaults | Urgent/High | ❌ Needs full planning | Open Q §A |
| 5 | TRN-210 captain-on-claude-backend | High | ❌ Needs assessment + planning | Open Q §B |
| 6 | TRN-168 opencode-backend-support | Medium | ⚠️ Needs minor tasks.md update | TRN-209 preferred first |
| 7 | TRN-212 test-coverage-gaps | Medium | ❌ Needs design + tasks | TRN-208, TRN-209 preferred first |
| 8 | TRN-213 config-install-consistency | Medium | ❌ Needs design + tasks | TRN-211 preferred first |
| — | TRN-206 raven-gateway-orientation | N/A | 🚫 CLOSE — superseded by TRN-214 | — |

---

## 4. Open Questions

These must be resolved by the Admiral or via architectural decision before the
corresponding planning work can complete.

### §A — TRN-207: Default exposure posture

The central design choice for network-exposure-defaults is the default bind/auth
posture. Three candidates:

1. **Loopback bind by default** — `ga-portal` binds `127.0.0.1:${PORT}`, requiring
   operators to explicitly choose a non-loopback bind and set `GA_API_KEY`. Least
   surprising, but a breaking change for remote-access deployments.
2. **Required API key for non-loopback binds** — install.sh refuses to start if
   `GA_API_KEY` is empty and the bind address is not loopback. Allows remote access
   but forces a key.
3. **Explicit insecure flag** — allow non-loopback without a key only when
   `GA_ALLOW_UNAUTHENTICATED=true` is set. Most permissive; makes the risk explicit.

A decision on posture drives scope and breaking-change communication for TRN-207.
The `X-Forwarded-For` rate-limit key (client-controlled) and the WebSocket
`forward_auth` bypass must also be reproduced on a disposable host before fix
approaches are locked in.

### §B — TRN-210: Dispatch mechanism for Claude backend

Two candidate approaches, both unconfirmed:

1. **`kirocrew spawn` named-persona dispatch (KiroCrew 0.8.0)** — if the CLI
   supports dispatching a named persona directly, Raven never needs to handle
   `.local_secret` at all. Needs verification against KiroCrew 0.8.0 changelog/source.
2. **Transport-side dispatch endpoint** — a new or existing transport endpoint that
   Captain calls, keeping credential handling out of the agent entirely. Scope and
   security model need definition.

A secondary question is whether persona prompts are actually delivered on the Claude
backend (KiroCrew 0.8.0 `claude-agent-acp` path). Raven's behaviour in the live
reproduction suggested they might not be — confirming this is a prerequisite for
knowing whether persona prompt delivery needs a separate fix.

### §C — TRN-212: Integration tests in CI

The proposal flags that integration tests currently run only by hand. Running the
real `install.sh` in a sandbox (stub `podman` on PATH, sandboxed HOME) in CI is
feasible but needs a decision on:

- Whether the CI environment can support a sandboxed Podman stub
- Whether integration tests gate PR merges or run on a scheduled basis only
- How Codex/Claude login tests (which require human interaction) are handled in
  automated runs

This decision sets the scope boundary for TRN-212's tasks.md.

---

*All line number references are to `ee0b3b8` (release/0.6.0) and may drift.*
