## 1. Extend backend validation to accept `opencode`

- [ ] 1.1 Add `opencode` to the valid backend names in `transport/config.py`'s `parse_agent_backends()` (alongside `kiro`, `claude`, `codex`)
- [ ] 1.2 Add `opencode` to `scripts/lib/agent_backends.sh` — it is validated against toolchain scripts, so adding `opencode.sh` in step 2 may be sufficient; confirm and add any explicit validation if needed
- [ ] 1.3 Update `tests/unit/test_agent_backends.py` with opencode validation scenarios (valid name accepted, unknown name still rejected, case normalisation)
- [ ] 1.4 Update `tests/unit/test_agent_backends_parity.py` to keep transport and shell validation in step

## 2. Add the OpenCode toolchain script

- [ ] 2.1 Create `crews/spec-ops/toolchains/opencode.sh` — install `opencode-ai` at a pinned version (`npm install -g opencode-ai@<version>`). Find the appropriate version from KiroCrew's `acp/harness/opencode.py` or install latest stable. Follow the same structure as `codex.sh` (`set -eu`, one install line).

## 3. Add login and logout routes for OpenCode

- [ ] 3.1 Add `POST /login/opencode` route in `transport/server.py` — follows the Claude login container pattern: refuse with HTTP 400 when opencode is not in the enabled set; when enabled, launch an ephemeral login container (`ga-opencode-login-*`) running the spec-ops image, exec `opencode auth login` inside it, capture `~/.local/share/opencode/auth.json` as `ga-opencode-auth`
- [ ] 3.2 Add `POST /logout/opencode` route — deletes `ga-opencode-auth`, available regardless of whether opencode is enabled (mirrors Claude's logout behaviour)
- [ ] 3.3 Add the disabled-backend check: `POST /login/opencode` with opencode not enabled returns HTTP 400 naming `GA_AGENT_BACKENDS`, checked before body validation

## 4. Inject credentials at crew launch

- [ ] 4.1 In `transport/lifecycle.py` (or wherever Claude's `ga-claude-auth` is mounted), add equivalent handling for `ga-opencode-auth` — untar it into the crew container's `~/.local/share/opencode/` at launch when opencode is enabled
- [ ] 4.2 Add the missing-credential check: if `GA_CREW_ACP_BACKEND=opencode` (or opencode is the requested backend) and `ga-opencode-auth` does not exist, return an error naming the login step, and do not start the crew

## 5. Update documentation

- [ ] 5.1 Update `docs/configuration.md` — add `opencode` to the `GA_AGENT_BACKENDS` valid values table, add `GA_CREW_ACP_BACKEND=opencode` example, note Preview status
- [ ] 5.2 Update `docs/auth.md` — add OpenCode login flow instructions (`POST /login/opencode`, `opencode auth login` command, `ga-opencode-auth` credential)
- [ ] 5.3 Update `config/ghostship.conf.example` — add commented `GA_AGENT_BACKENDS=opencode` example

## 6. Tests and verification

- [ ] 6.1 Add unit tests for the new `/login/opencode` and `/logout/opencode` routes — disabled-backend rejection, login container launch, logout credential deletion
- [ ] 6.2 Add unit test: `GA_CREW_ACP_BACKEND=opencode` with no `ga-opencode-auth` → launch fails with descriptive error
- [ ] 6.3 Manual smoke test: build spec-ops image with `GA_AGENT_BACKENDS=opencode`, run login flow, launch a crew, verify `opencode acp` session starts and Crew tools are available
