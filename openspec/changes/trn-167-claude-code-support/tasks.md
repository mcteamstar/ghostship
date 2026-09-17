## 1. Image Layer — Claude Toolchain

- [ ] 1.1 Add `INCLUDE_CLAUDE_AGENT` build arg to `crews/spec-ops/Containerfile`; when `true`, install `claude-agent-acp` and `claude` CLI at pinned versions (confirm exact package name and version from npm before pinning)
- [ ] 1.2 Confirm the headless tool-approval suppression mechanism for `claude-agent-acp` (check package docs/source for env var or flag); document the chosen approach in a comment in the Containerfile
- [ ] 1.3 Add `GA_INCLUDE_CLAUDE_AGENT` resolution to `scripts/install.sh`; pass `--build-arg INCLUDE_CLAUDE_AGENT=true` to the spec-ops image build when set

## 2. Transport Config

- [ ] 2.1 Add `GA_CREW_ACP_BACKEND` to `transport/config.py` (valid values: `"kiro"`, `"claude"`; default: `"kiro"`); validate at startup and exit on unrecognised value
- [ ] 2.2 Add `GA_CREW_ANTHROPIC_API_KEY` to `transport/config.py`; validate that it is set when `GA_CREW_ACP_BACKEND=claude` (fail at launch time if absent)
- [ ] 2.3 Add `GA_INCLUDE_CLAUDE_AGENT` to `transport/config.py` (boolean; default `false`)

## 3. Crew Lifecycle — Auth and Config Patching

- [ ] 3.1 In `_patch_crew_config`, write `acp_backend: "claude"` into the crew config when `GA_CREW_ACP_BACKEND=claude`
- [ ] 3.2 In `inject_auth.py` (or the equivalent call site in the launch path), add a Claude backend branch: when `GA_CREW_ACP_BACKEND=claude`, skip all kiro-cli auth injection and instead inject `ANTHROPIC_API_KEY` from `GA_CREW_ANTHROPIC_API_KEY` as a container env var
- [ ] 3.3 Inject the headless approval suppression env var/flag (identified in task 1.2) into Claude-backend crew containers at creation time
- [ ] 3.4 Emit a WARNING-level log entry at `launch` time when `GA_CREW_ACP_BACKEND=claude` naming `api.anthropic.com` as a required outbound destination

## 4. Registry and API

- [ ] 4.1 Record `acp_backend` in the crew's `crews.json` entry at launch time (value: the resolved `GA_CREW_ACP_BACKEND`, defaulting to `"kiro"`)
- [ ] 4.2 Include `acp_backend` in the `crews()` MCP tool response for each crew entry; omit or default to `"kiro"` for pre-TRN-167 entries without the field

## 5. Docs and Config

- [ ] 5.1 Add `GA_CREW_ACP_BACKEND`, `GA_CREW_ANTHROPIC_API_KEY`, and `GA_INCLUDE_CLAUDE_AGENT` to `docs/configuration.md` with defaults, valid values, and dependency notes
- [ ] 5.2 Add commented-out entries for all three env vars to `config/ghostship.conf.example`
- [ ] 5.3 Add a note to `docs/architecture.md` documenting the Claude backend governance gap: KiroCrew's per-call tool approval gate is bypassed, but the signed security policy ceiling is still enforced
- [ ] 5.4 Add a note to `docs/architecture.md` documenting the `api.anthropic.com` external network requirement for Claude-backend crews

## 6. Tests

- [ ] 6.1 Add unit tests for `GA_CREW_ACP_BACKEND` config validation (invalid value → startup error; `claude` without API key → launch error)
- [ ] 6.2 Add a test asserting that `_patch_crew_config` writes `acp_backend: "claude"` when the Claude backend is selected
- [ ] 6.3 Add a test asserting that kiro auth injection is skipped and `ANTHROPIC_API_KEY` is injected when `GA_CREW_ACP_BACKEND=claude`
- [ ] 6.4 Add a test asserting that `crews()` response includes `acp_backend` per crew
