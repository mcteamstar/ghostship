# Tasks

## 1. Toolchain

- [x] 1.1 Add `crews/spec-ops/toolchains/claude-managed-settings.json` with exactly `{"attribution": {"commit": "", "pr": ""}}` (design Decision 2). In `claude.sh`, after the npm installs, install it to `/etc/claude-code/managed-settings.json` (mode 0644) and add a header comment explaining why it sits outside the home volume. Verify: `sh -n crews/spec-ops/toolchains/claude.sh` passes, and `python3 -m json.tool` parses the JSON file.
- [x] 1.2 Unit test in `tests/unit/` that loads the JSON file and asserts that `attribution.commit` and `attribution.pr` are both `""`, that `includeCoAuthoredBy` is absent, and that `claude.sh` references the file and `/etc/claude-code/managed-settings.json`. Verify: the test passes, and fails if either string is made non-empty.
- [x] 1.3 The file is installed only by `claude.sh`, so an image without the claude toolchain never gets it. Verify: `grep -rn managed-settings crews/` has references only in `claude.sh` (the JSON has no `managed-settings` key); `test -f crews/spec-ops/toolchains/claude-managed-settings.json`; and the `Containerfile` loop invokes only `/tmp/toolchains/$name.sh` for selected `AGENT_TOOLCHAINS` before removing `/tmp/toolchains`, so an empty or non-claude toolchain list leaves no managed-settings file in the final image.

## 2. Docs

- [x] 2.1 In `docs/configuration.md`, next to `GA_GIT_AUTHOR_*`, add a note that the git identity and Claude attribution are separate, and that claude crews add no `Co-Authored-By` trailer or PR attribution (baked into the image). Add the same note to the "Git author identity" section of the ghostship-command skill (`.claude-plugin/skills/ghostship-command/SKILL.md`), and update that section's Option 1 while there: it still shows `GA_GIT_AUTHOR_*` in `ghostship.conf` and `./install.sh --config ghostship.conf`, which predate the YAML config. Replace it with `crew.git.author.name` / `crew.git.author.email` in `config/ghostship.yaml` followed by `ghostship upgrade`. Verify: both notes are present, and `grep -n 'ghostship.conf' .claude-plugin/skills/ghostship-command/SKILL.md` no longer matches the git-identity section.
- [x] 2.2 Add a CHANGELOG entry in a new `## v0.8.1` section above `## v0.8.0` (create it if no 0.8.1 section exists yet): claude crews no longer add Claude Code attribution to commits or PRs, and existing claude crews need relaunching after `ghostship upgrade`. Verify: the entry is present.

## 3. Integration check

- [x] 3.1 Run the full unit suite. Verify: `scripts/run.sh --unit` exits 0.
- [x] 3.2 On the live install after `ghostship upgrade`:
  - Launch a claude crew, supply a small git repo, and dispatch ghost to commit a one-line change.
  - Evac the bundle and inspect the commit. Verify: the message has no `Co-Authored-By` line.
  - Result (2026-10-20, transport and image at `098e73e`, KiroCrew 0.9.0): the rebuilt `spec-ops` image carries `/etc/claude-code/managed-settings.json` = `{"attribution": {"commit": "", "pr": ""}}`. On a claude crew (Claude Haiku 5.5), ghost was asked to commit a one-line README change "the way you normally commit", with no mention of attribution. The evac'd commit object (`2449939`, message `docs: add ghost check line to README`) has no `Co-Authored-By` line and no "Generated with Claude Code" text. Before this change, claude-crew commits carried `Co-Authored-By: Claude Haiku 5.5`.
