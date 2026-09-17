## Context

KiroCrew 0.6.0 added a selectable ACP backend system. Each crew's config can declare `acp_backend: "claude"` to switch from kiro-cli to `claude-agent-acp` as the session runtime. Ghostship 0.5.x has no awareness of this field: `_patch_crew_config` never writes it, crew images don't include the Claude toolchain, and there's no mechanism to supply an Anthropic API key to a crew container. See proposal.md for motivation.

Current auth injection path (kiro): `inject_auth.py` reads `ga-kiro-auth` or `KIRO_API_KEY` and writes into the crew's kiro-cli SQLite DB. This path is kiro-specific and must be bypassed entirely for Claude crews.

The spec-ops `Containerfile` currently installs Node.js 24 LTS (for the OpenSpec CLI), so `npm install` is available without new base layer changes. The `claude-agent-acp` npm package and `claude` CLI both install cleanly via npm.

## Goals / Non-Goals

**Goals:**
- Allow operators to opt in to Claude Code as the ACP backend via `GA_CREW_ACP_BACKEND=claude`
- Inject `ANTHROPIC_API_KEY` into Claude-backend crews; skip all kiro-cli auth
- Keep the default image lean — Claude toolchain is opt-in at build time via `GA_INCLUDE_CLAUDE_AGENT`
- Surface backend selection in `crews()` and record it in `crews.json`
- Emit a startup warning about `api.anthropic.com` external network dependency

**Non-Goals:**
- Per-crew backend selection (backend is transport-wide via `GA_CREW_ACP_BACKEND`; mixing kiro and Claude crews in the same transport instance is out of scope)
- opencode or other ACP backends (TRN-168)
- Rotating the Anthropic API key in running crews without restart
- Making Claude Code work through KiroCrew's per-call tool approval gate (known gap; documented)

## Decisions

### D1: Transport-wide backend flag, not per-launch parameter

`GA_CREW_ACP_BACKEND` is an env var resolved at transport startup, not a `launch` parameter. This is simpler and consistent with how other transport-wide settings (`KIRO_API_KEY`, `GA_SPAWN_MIN_MEMORY_GB`) work. A per-launch `acp_backend` parameter would allow mixing backends in one transport instance, but the auth injection logic (`inject_auth.py`) and image requirements differ between backends — mixing without careful isolation creates failure modes that aren't worth the complexity at this stage.

**Alternative considered:** `acp_backend` as a `launch` parameter. Rejected: the spec-ops image must be built with the Claude toolchain to support Claude crews; if the image doesn't have it, a per-launch flag is useless. Tying the image build flag and the runtime flag together at the transport level makes the pairing clear.

### D2: Opt-in image layer via INCLUDE_CLAUDE_AGENT build arg

`claude-agent-acp` + `claude` CLI add ~200-400 MB to the image. Making this opt-in keeps the default image lean for operators who only use kiro-cli. The build arg is controlled by `GA_INCLUDE_CLAUDE_AGENT` in `ghostship.conf`, passed to `podman build` in `install.sh`.

**Alternative considered:** Always include the Claude toolchain. Rejected: unnecessary size increase for the majority of installs; pinning exact versions also makes a "always-included" approach fragile as the package evolves.

### D3: ANTHROPIC_API_KEY injected as env var, not a Podman secret

`KIRO_API_KEY` is currently handled as an env var in crew containers (not via Podman secrets). For consistency and simplicity, `ANTHROPIC_API_KEY` follows the same pattern. The key is sourced from `GA_CREW_ANTHROPIC_API_KEY` on the transport and injected directly at container creation time via `--env ANTHROPIC_API_KEY=<value>`.

**Alternative considered:** Podman secret. The Podman secrets API is already used for `ga-api-key` on the transport, but crew containers are not currently wired for per-crew secrets. Adding that machinery for one key is disproportionate effort; the env var approach is consistent with the existing kiro API key path.

**Security note:** `ANTHROPIC_API_KEY` will be visible via `podman inspect` on the crew container (same as `KIRO_API_KEY` today). This is a known limitation; the container-level boundary is the security perimeter.

### D4: Claude Code headless mode via CLAUDE_SKIP_TOOL_APPROVAL env var

Research (TRN-167 Ghost report) identified that `dangerously_skip_permissions=True` in KiroCrew bypasses KiroCrew's gate but not Claude Code's own internal approval layer. To prevent headless stalls, inject the appropriate env var/flag to suppress Claude Code's approval prompts. The exact mechanism (`CLAUDE_SKIP_TOOL_APPROVAL`, `--dangerously-skip-permissions` CLI flag, or `claude-agent-acp` config) must be confirmed against the `claude-agent-acp` package docs during implementation; record the chosen approach in a comment in `inject_auth.py`.

### D5: Startup validation, not launch-time validation, for backend/key pairing

If `GA_CREW_ACP_BACKEND=claude` and `GA_CREW_ANTHROPIC_API_KEY` is unset, fail at transport startup (or on first `launch` call) rather than silently creating crews that will fail at session time. This surfaces the misconfiguration early. A startup check is preferred — but since the transport currently doesn't hard-fail on config validation, a `launch`-time check is an acceptable fallback if startup validation requires more refactoring than the change warrants.

## Risks / Trade-offs

- **External network dependency** → Claude Code calls `api.anthropic.com` directly from inside crew containers. Behind enterprise firewalls that block external HTTPS egress, Claude crews will silently fail at session time. Mitigation: emit a WARNING at launch time; document in `docs/architecture.md`.

- **Headless stall risk** → If the Claude Code headless approval suppression mechanism is wrong or incomplete, agent sessions will stall waiting for interactive input that never comes. Mitigation: test with a real dispatch before shipping; verify the mechanism in the integration test.

- **Image build coupling** → Operators must rebuild the spec-ops image (`./install.sh`) to get the Claude toolchain, even if they already have a running transport. This is consistent with how other image changes work (persona updates require reinstall) but may surprise operators who expect `GA_CREW_ACP_BACKEND=claude` to "just work" without a reinstall. Mitigation: document clearly in the config docs.

- **Version pinning maintenance** → `claude-agent-acp` and the `claude` CLI are pinned in the Containerfile. Keeping these current requires a manual bump + rebuild cycle. Mitigation: document the update procedure; consider a dependabot entry for the Containerfile.

## Migration Plan

1. Build the Claude-enabled image: add `GA_INCLUDE_CLAUDE_AGENT=true` to `ghostship.conf`, re-run `./install.sh`.
2. Set `GA_CREW_ACP_BACKEND=claude` and `GA_CREW_ANTHROPIC_API_KEY=<key>` in `ghostship.conf`.
3. Restart the transport: `ghostship stop && ghostship start`.
4. Verify: `launch` a new crew and `dispatch` a trivial ghost task; confirm it completes without stalling.

Existing kiro-backend crews are unaffected — backend selection applies to newly launched crews only. A mixed fleet (old kiro crews + new claude crews) is safe as long as the image used for the new crews has the Claude toolchain.

**Rollback:** Set `GA_CREW_ACP_BACKEND=kiro` (or unset it) and restart the transport. Existing Claude crews that are already running will continue to function until nuked; no in-place migration of running crews is needed.

## Open Questions

- What is the exact env var or flag name that `claude-agent-acp` uses to suppress interactive tool approval in headless mode? Confirm against the `claude-agent-acp` package source/docs during Task A (image layer). If no clean suppression mechanism exists, escalate before implementing auth injection.
