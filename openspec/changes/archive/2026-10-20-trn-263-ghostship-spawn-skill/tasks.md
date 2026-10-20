# Tasks

## 1. The ghostship-spawn skill

- [x] 1.1 Add `academy/skills/ghostship-spawn/scripts/ghostship-spawn` (mode 0755, Python 3, standard library only) per design Decision 1:
  - the fixed `http://localhost:5476` base;
  - validated persona and task id;
  - `<persona>`, `--status`, `--steer` and `--continue` forms;
  - cookie-only auth with `Origin` from `KIROCREW_CORS_ORIGINS`;
  - JSON response on stdout, and a one-line stderr error with exit 1 on any failure, with the cookie never in any output.
  Verify: unit tests in `tests/unit/test_ghostship_spawn.py`, against a local HTTP stub and a temp cookie file, cover:
  - each form's method, path and body;
  - empty stdin rejected with no request made;
  - an invalid persona or task id rejected;
  - a non-2xx reported with status and body;
  - the cookie absent from stdout and stderr in every case;
  - no argument or environment variable changes the request host, port or path.
- [x] 1.2 Add `academy/skills/ghostship-spawn/SKILL.md` in the style of `ghostship-mail`:
  - front-matter with `name`, a `description` saying when to use it, `allowed-tools` for the script path, and `metadata`;
  - the four forms with examples, using heredoc stdin;
  - the JSON output and how to read the gateway response's `id` field as the task ID;
  - "keep briefs short and describe commands, don't quote them";
  - "on a claude crew a refusal is a gate block: report and hold".
  Verify: `tests/unit/test_skill_contracts.py` (or the existing skill front-matter test) passes for the new skill.

## 2. Skill delivery

- [x] 2.1 Change `AcademyLoader._copy_skills` (`transport/academy.py`) to copy every regular file under each selected skill directory in one tar per skill, keeping relative paths, skipping symlinks and special files, with `0o755` for executable sources and `0o644` otherwise (design Decision 3). Verify: unit tests with a fake Podman client cover:
  - a skill with `SKILL.md` plus `scripts/x` (0755) produces tar members `SKILL.md` (0644) and `scripts/x` (0755);
  - a `SKILL.md`-only skill produces the same single member as before;
  - a symlink in the skill directory is skipped;
  - the manifest filter still applies.

## 3. Prompts and templates

- [x] 3.1 Rewrite `_RAVEN_GATEWAY_ORIENTATION` (`transport/captain.py`) and the gateway paragraph of `academy/agents/raven.json` per design Decision 4:
  - `kirocrew` for routine operations, `ghostship-spawn` for dispatch, status, steer and continue;
  - brief hygiene;
  - refusal handling with no "approve" option and no quoted command;
  - report and hold if the skill is missing.
  Remove the cookie path, `curl` and the internal-header text. Verify: the guard test in 3.3 passes.
- [x] 3.2 In `academy/orders/spec-driven-development.md` (around line 60) and `academy/orders/independent-review.md` (around line 15), replace the `/api/spawn` + `X-Internal-Secret`/`X-Session-Key` instruction with "dispatch with `ghostship-spawn <persona>` and write the confirmation marker with the gateway response's `id` field as the task ID". Keep the intent and idempotency protocol unchanged. Verify: the guard test in 3.3 passes, and the existing template tests in `tests/unit/test_captain.py` pass.
- [x] 3.3 Add the guard test from design Decision 5. It loads `raven.json`, `_RAVEN_GATEWAY_ORIENTATION`, every `academy/orders/*.md` (raw and after `_substitute_placeholders`) and the resolved check-in task text, and asserts that:
  - none contains `.local_secret`, `X-Internal-Secret`, `X-Session-Key`, `.dashboard_cookie`, `curl`, `-d @`, `--data @` or `--data-binary @`;
  - each mentions `ghostship-spawn`.
  Verify: it fails on the current `spec-driven-development.md` and passes after 3.1 and 3.2.

## 4. Docs and checks

- [x] 4.1 Correct the claude permission comment in `crews/spec-ops/toolchains/claude.sh`: claude crews run in KiroCrew's `default` mode under its hook gate, and `dangerously_skip_permissions` only approves what the gate allows. Add the same note, plus a short `ghostship-spawn` section, to `docs/architecture.md`. Fix the `KC_BASE_IMAGE` default note in `docs/configuration.md` to the pinned 0.9.0 digest. Add a CHANGELOG entry in a `## v0.8.1` section (create it if absent) covering the new skill and that Raven dispatch no longer stalls on claude crews. Verify: `grep -n bypassPermissions crews/spec-ops/toolchains/claude.sh` no longer claims KiroCrew writes it; the CHANGELOG entry is present.
- [x] 4.2 Run the full unit suite. Verify: `scripts/run.sh --unit` exits 0.
- [x] 4.3 On the live install after `ghostship upgrade`:
  - Launch a claude crew and supply the repo.
  - Order Captain with `specky` on a small change.
  - Confirm through the transport only (`captain status`, `pickup`, `crews()`) that Raven dispatches ghost with `ghostship-spawn` on the first check-in, with no refusal, and that a `dispatching ghost <task_id>` confirmation marker appears.
  Then dispatch a raven task over MCP to report `ls -l ~/.kiro/crew/skills/ghostship-spawn/scripts/`. Verify: the script is present and executable.
  - Result (2026-10-20, transport at `b098153`, claude crew on KiroCrew 0.9.0): the skill was delivered and the script is executable in `~/.kiro/crew/skills/ghostship-spawn/scripts/`. At the second check-in Raven dispatched ghost (`1cde8f4be4d3b618`) with `ghostship-spawn`, with no refusal, and wrote both the intent and the `dispatching ghost 1cde8f4be4d3b618` confirmation markers. Caveat: at the first check-in Raven held, because claude sessions don't list academy skills in their Skill tool (issue #30), and it went ahead only after being told to call the helper by its path.
