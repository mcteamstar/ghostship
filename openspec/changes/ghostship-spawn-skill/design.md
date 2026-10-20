# Design

## Context

See proposal.md for why. All KiroCrew facts below were checked against the exact source in the pinned base image (`ghcr.io/kirodotdev/kirocrew@sha256:108e6b94…`, label `org.opencontainers.image.version=0.9.0`, revision `99e6253`). Paths are relative to the installed `kiro_crew` package.

- **The claude tool gate.** Claude-backend Bash calls arrive as `session/request_permission` and run the hook gate before any grant (`subagent_manager/run.py:2715`, `tool_permission.py:384-420`). Its tiers run in this order: unverifiable-shell, targets (sensitive-path, sensitive-bash, exfil), param-paths, write-protected, deny-rules, governance, then auto-approve tiers (`hooks.py:2725-2745`). `dangerously_skip_permissions` is a grant that is consulted only after those tiers, and deny tiers can't be overridden (`hook_runtime/gate_tiers.py:324-333`).
- **The exfiltration tier.** It does a case-insensitive substring match on the normalised title and the raw command, heredoc bodies included, for `-d @`, `--data-binary @` (`@-` too), `--upload-file`, `-F *=@`, `/dev/tcp/` and others (`security/exfil.py:1907-1945`, `gate_tiers.py:114-129`). Rule id: `data-exfil-curl-file-body`.
- **Other tiers.** Built-in `curl .* \| sh` / `\| bash` are unanchored and multi-line (`security/denied_rules.py:1121-1137`). The Bash scan limit is 20,480 chars (`security/paths.py:1356`). Shell command text is not path-matched, and `.dashboard_cookie` appears nowhere in KiroCrew (`gate_tiers.py:393-412`).
- **Rejections and audit.** Claude rejections are a bare `reject` with no reason (`acp/client.py:9424-9441`; reasons are sent only to kiro/kas, `agent_sdk/backends.py:1090`). The SEL row says `error=hook_deny` with no reason (`tool_permission.py:742-795`).
- **What the gate sees and what the loader reads.** The gate inspects only the call's title and command string. It doesn't resolve scripts or child processes, and nothing fences `~/.kiro/crew/skills/`. KiroCrew's loader reads `SKILL.md` and leaves other files in a skill directory alone (`skills.py:1105-1135`).
- **The kirocrew CLI.** `kirocrew spawn run` takes only `[--async] task`, so there is no persona selection. Named dispatch needs `POST /api/spawn` with `agent`, which Raven has used successfully.
- **ghostship today.** `AcademyLoader._copy_skills` (`transport/academy.py:482`) tars only `SKILL.md` into `/home/kirocrew/.kiro/crew/skills/<name>/`. `_RAVEN_GATEWAY_ORIENTATION` (`transport/captain.py:54`) and `raven.json` describe a hand-built cookie `curl` call. The order templates (`spec-driven-development.md:60`, `independent-review.md:15`) contradict them with `X-Internal-Secret`.

## Goals / Non-Goals

**Goals:**
- Gateway operations become one fixed command whose command line the gate never objects to, however the model phrases its call.
- One authoritative source for how the call is authenticated.

**Non-Goals:**
- Changing KiroCrew's gate, the exfil rule set or the security policy deny list.
- Using the helper as a generic HTTP client. It reaches one destination only.

## Decisions

### 1. Helper is a fixed-destination Python program (Admiral sign-off)
`scripts/ghostship-spawn` is a Python 3 program that uses only `urllib.request` and the standard library, no `curl`.
- **Destination.** The base URL is a constant, `http://localhost:5476`, and the paths are built only from the subcommand and a `task_id` validated against `^[A-Za-z0-9_-]{1,64}$`. Nothing in argv, stdin or the environment can change host, port or path.
- **Auth.** It reads `/home/kirocrew/.kiro/crew/.dashboard_cookie`, validates the value as a bounded RFC 6265 cookie value, and sends `Cookie: mc_token_5476=<value>`, plus `Origin` taken from the first entry of `KIROCREW_CORS_ORIGINS`, falling back to `http://localhost:5476`. `Origin` is a header, not the destination.
- **Bodies.**
  - dispatch: `{"task": <stdin>, "agent": <persona>, "keep": true}` so the run remains available for status, steering and continuation;
  - steer: `{"message": <stdin>}`
  - continue: `{"task": <stdin>}`
  - `--status` sends a GET with no body.
- **Persona.** Validated against `^[a-z][a-z0-9-]{0,31}$`; the gateway decides whether the persona exists.
- **Output.** The gateway response body goes to stdout unchanged; the dispatch task ID is its `id` field. On a non-2xx, redirect, connection or cookie error, it prints `ghostship-spawn: <op> failed: HTTP <status>: <body>` (or the error) to stderr, exits 1, and never includes the cookie. The HTTP client does not follow redirects, so a response cannot move the request away from the fixed loopback destination.

The exfil tier never sees this body, by design. That is acceptable only because the destination is fixed to the crew's own loopback gateway. The Admiral signed off on this exception in place of disabling `data-exfil-curl-file-body` crew-wide (which would weaken it for every agent and destination) or relying on inline-JSON quoting (which is what drifts).

### 2. Invocation by absolute path, declared in the skill
Raven runs `~/.kiro/crew/skills/ghostship-spawn/scripts/ghostship-spawn …`, and `SKILL.md` gives that exact path. Adding it to `PATH` would mean overriding the container's `PATH` at create time or editing the image, and neither is needed: the path is fixed, and the 0.9.0 gate doesn't fence it. `SKILL.md` declares `allowed-tools: Bash(~/.kiro/crew/skills/ghostship-spawn/scripts/ghostship-spawn:*)`, in the style of `ghostship-mail`.

*Alternative:* bake `/usr/local/bin/ghostship-spawn` into the image. Rejected, because the script would then ship separately from its instructions and need an image rebuild to change.

### 3. Skill copy walks the directory
`_copy_skills` builds one tar per skill containing every regular file under the skill directory, with relative paths kept and symlinks and special files skipped. It sets `mode=0o755` on files that are executable in the source and `0o644` on the rest, then sends one `container_archive_put` to `/home/kirocrew/.kiro/crew/skills/<name>`. `SKILL.md`-only skills produce a tar identical to today's.

### 4. One description of gateway operations, used everywhere
`_RAVEN_GATEWAY_ORIENTATION` and the `raven.json` prompt are rewritten to say:
- use `kirocrew` for list, cron, pause and resume;
- use the `ghostship-spawn` skill for dispatch, status, steer and continue;
- keep briefs short and describe commands rather than quoting them;
- a refused call is a gate block, so report the operation and hold, and never offer an "approve" option or quote the command into mail;
- if the skill is missing, report and hold.

Both templates keep their intent protocol but replace the auth sentence with "dispatch with `ghostship-spawn <persona>` and record the gateway response's `id` field as the task ID". The cookie path, `curl` and every internal-header mention are removed from all prompt sources.

### 5. Guard test across all prompt sources
One unit test loads `raven.json`, `_RAVEN_GATEWAY_ORIENTATION`, every `academy/orders/*.md`, both raw and after `_substitute_placeholders`, and the resolved `_CAPTAIN_CHECKIN_TASK`. It asserts that none contains `.local_secret`, `X-Internal-Secret`, `X-Session-Key`, `.dashboard_cookie`, `curl` or any exfil data-file pattern, and that each source mentions `ghostship-spawn`.

## Risks / Trade-offs

- [The brief itself trips a tier: an exfil substring, `curl … | sh`, or more than 20 KiB] → The prompts tell Raven to describe rather than quote and to keep briefs short. A refusal is reported, not looped.
- [The exception hides one helper's body from the exfil tier] → The destination is a hard-coded loopback gateway, with no caller-supplied URL. The Admiral signed off, and the decision is recorded here.
- [A newer KiroCrew fences `~/.kiro/crew/skills/` or changes the loader] → The live check (task 4.2) covers the pinned image. Re-check when `KC_BASE_IMAGE` is bumped.
- [Any persona can dispatch] → No new access, since the cookie is already readable by agents. The decision is recorded.

## Migration Plan

Transport and academy only: `ghostship upgrade` rebuilds the transport, which carries the academy. Relaunch crews to get the skill and the new `raven.json`. New Captain orders resolve the new templates. A crew that has the old prompts but no skill behaves as it does today. Rollback is reverting the commit and upgrading again.
