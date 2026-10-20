# Proposal

## Why

On claude-backend crews, Raven's dispatch of named personas fails intermittently with "User refused permission to run tool", which stalls Captain autopilot. TRN-258's first crew and TRN-262's crew both stalled this way. The cause comes from the setup, but which form the model happens to write decides when it shows up:

- Claude crews do not run in `bypassPermissions`. KiroCrew 0.9.0 never writes that mode; it writes `auto` only when that is asked for. Every Bash call therefore arrives as a permission request and passes through KiroCrew's hook gate, and `dangerously_skip_permissions` only grants approval after the gate's deny tiers, which it cannot override.
- Raven rebuilds the `curl` call to `/api/spawn` from prose on every check-in. Some versions trip a gate check. The always-on exfiltration check (`security/exfil.py` in 0.9.0) does a case-insensitive substring match on the raw command, heredoc bodies included, for `-d @`, `--data-binary @` (including `@-`) and similar patterns, while an inline `-d '{…}'` body passes. A mail that quoted the command was refused for the same reason. On claude crews the rejection carries no reason, so the adapter reports "User refused permission to run tool", and Raven reads it as a human refusal and holds.
- The instructions contradict each other. The persona prompt and the check-in orientation say cookie only and never `X-Internal-Secret`, while both order templates say to pass `X-Internal-Secret` from `.local_secret` and `X-Session-Key`. That breaks the existing "persona prompt and task text agree" requirement and leaves Raven to improvise.

Separately from the gate problem, agents shouldn't be assembling authenticated gateway calls from prose at all. `ghostship-mail` gives every agent one sanctioned way to send mail. Gateway operations deserve the same, a single tested helper that gets them right every time, and that is the main reason for this change. The gate fix comes with it.

## What Changes

- New academy skill `ghostship-spawn`, a sibling of `ghostship-mail`. It contains a `SKILL.md` and a `ghostship-spawn` script that wraps the four gateway operations the `kirocrew` CLI can't do: dispatch a named persona, get task detail, steer, and continue.
  - The script is a small Python program (standard library only, no `curl`) that talks only to the crew's own gateway at the fixed loopback address, `localhost:5476/api/spawn…`. It reads `.dashboard_cookie` and sets `Origin` itself, uses cookie-only auth, and takes the task or message text on stdin.
  - **Deliberate exception, signed off by the Admiral:** the gate checks only the agent's command line, so the helper's request body is not scanned by the exfiltration check. That is acceptable because the destination is fixed to the crew's own loopback gateway, so the helper cannot be used as a general upload path.
  - It prints the gateway's JSON reply and never prints the cookie.
  - Raven's tool call becomes `ghostship-spawn <persona> <<'EOF' … EOF`, with no `curl`, no `@file` and no secret in the command line the gate inspects.
- Skill delivery copies the whole skill directory, not only `SKILL.md`, and keeps executable files executable. `ghostship-spawn` is the first skill to ship a script.
- `raven.json`, `_RAVEN_GATEWAY_ORIENTATION` and both order templates (`spec-driven-development`, `independent-review`) send Raven to the skill instead of describing a `curl` call. Every `.local_secret` / `X-Internal-Secret` / `X-Session-Key` reference is removed.
- Raven is told what a refusal on a claude crew means: a gate block, not a human decision. It reports the operation and holds, without asking for approval, and doesn't quote command lines into mail.
- Corrected documentation of the claude permission model (`crews/spec-ops/toolchains/claude.sh`, `docs/architecture.md`): claude crews run in KiroCrew's `default` mode under its hook gate. The `KC_BASE_IMAGE` digest note in `docs/configuration.md` is corrected to the pinned 0.9.0 digest.
- Raven's briefs stay short and describe commands rather than quoting them, because the brief is in the heredoc the gate scans. If `ghostship-spawn` is missing, Raven reports and holds instead of building a `curl` call.
- Out of scope:
  - KiroCrew passing the deny reason back to the adapter (an upstream issue).
  - A native `kirocrew spawn run --agent` (upstream; 0.9.0's `spawn run` takes only `[--async] task`).
  - Any change to the security policy deny list.

## Upstream follow-ups (KiroCrew, not this change)

The helper removes ghostship's exposure. The underlying gaps are in KiroCrew 0.9.0:

1. **No deny reason for claude.** Gate rejections reach kiro and kas sessions with the reason (for example `Blocked: command matches data-exfiltration pattern '-d @'`), so those agents correct themselves. Claude sessions get a bare reject that the adapter reports as a human refusal. Passing the reason through would let claude agents recover the same way. This is the main cause of the stall.
2. **No native named-persona dispatch.** `kirocrew spawn run` has no `--agent`, so agents can only reach other personas through hand-built REST calls. A CLI flag or in-session tool would let `ghostship-spawn` become a thin wrapper or be removed.
3. **The exfiltration rule ignores the destination.** It refuses a file-body upload to the crew's own loopback gateway just as it would one to an external host. A loopback exemption would make the signed-off exception in this change unnecessary.

## Capabilities

### New Capabilities
- `persona-dispatch`: the in-crew helper contract for dispatching, inspecting, steering and continuing named persona tasks on the crew's own gateway (inputs, output, auth, error reporting, secret handling).

### Modified Capabilities
- `autonomous-orchestration`: "Raven persona prompt uses cookie-only auth for spawn calls" becomes "Raven performs gateway operations through the ghostship-spawn skill". The cookie-only rule moves into the helper, and the requirement that all prompt sources agree now covers the order templates too.
- `agent-personas`: the Raven requirement's scenario "Raven's lean prompt still covers gateway auth" (which still says `.local_secret`) now points at the skill.
- `crew-manifest`: skill copying delivers every file in a selected skill directory, keeping the executable bit.

## Impact

- **Code:** `academy/skills/ghostship-spawn/` (new); `transport/academy.py` (`AcademyLoader` skill copy); `transport/captain.py` (`_RAVEN_GATEWAY_ORIENTATION`); `academy/agents/raven.json`; `academy/orders/spec-driven-development.md` and `independent-review.md`.
- **Tests:** unit tests for the helper (argument handling, request shape, no cookie in output), for the directory copy and file modes, and a content check that no persona prompt, orientation or order template mentions `.local_secret`, `X-Internal-Secret`, `X-Session-Key` or `-d @`.
- **Docs:** `crews/spec-ops/toolchains/claude.sh` comment, `docs/architecture.md`, `docs/configuration.md`, CHANGELOG.
- **Operators:** relaunch crews to pick up the skill. Existing crews keep their copied skills and old prompts. No config change.
- **Risks:**
  - Task text is still scanned. A brief that quotes an exfiltration-shaped string (`-d @…`, `curl … | sh`, `/dev/tcp/`) or exceeds 20 KiB is still refused. The prompts tell Raven to avoid that, and the refusal is reported rather than escalated.
  - Every persona can use the skill (`skills: "*"`). That grants no new access, since any agent can already read the cookie and call the gateway, and the skill declares `allowed-tools: Bash(ghostship-spawn:*)`.
- **Related:** unblocks `trn-262-claude-no-coauthor-trailer` on Captain autopilot. TRN-262's managed settings must not set `permissions`.
