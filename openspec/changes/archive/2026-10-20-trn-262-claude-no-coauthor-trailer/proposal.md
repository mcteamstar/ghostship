# Proposal

## Why

Claude-backend crews add Claude Code's attribution to the work they hand back: a `Co-Authored-By: Claude <model>` trailer on every commit (seen on TRN-258's review commit `27af6a3`) and "Generated with Claude Code" text in PR bodies. Those commits are evac'd and cherry-picked into the operator's repo, so the attribution ends up in real history and has to be stripped by hand. `crew.git.author` in `ghostship.yaml` sets the git identity only. The trailer is written into the message by the agent, as Claude Code's own default, so nothing ghostship configures today removes it.

## What Changes

- The claude toolchain (`crews/spec-ops/toolchains/claude.sh`) bakes a Claude Code managed settings file into the crew image that turns off commit and PR attribution.
- The file lives outside the crew's home volume (`/home/kirocrew`), so every crew launched from the image gets it. That includes crews whose home volume already exists, and it survives anything that rewrites `~/.claude/` (OAuth credential injection).
- Managed settings take precedence over user, project and session settings, so a session's `.claude/settings.local.json` (which KiroCrew writes for `bypassPermissions`) cannot turn attribution back on.
- Images built without the claude toolchain are unchanged.
- Out of scope: the git author identity. Operators still set `crew.git.author.name` / `.email` for that. Kiro and codex backends, which don't add this trailer.
- Existing crews keep the image they launched with. They pick up the setting only after an image rebuild (`ghostship upgrade`) and a relaunch.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `crew-image-build`: adds a requirement that an image built with the claude toolchain disables Claude Code commit and PR attribution through managed settings.

## Impact

- **Code:** `crews/spec-ops/toolchains/claude.sh` (write the managed settings file at build time).
- **Tests:** a build-content check that the file exists in a claude-toolchain image with the expected keys, and is absent from an image built without the toolchain.
- **Docs:** `docs/configuration.md` next to `GA_GIT_AUTHOR_*` (identity and attribution are separate, and attribution is off by default for claude crews); the ghostship-command skill's "Git author identity" section, whose config example still predates the YAML config; CHANGELOG (v0.8.1).
- **Operators:** run `ghostship upgrade` to rebuild the image, then relaunch claude crews. No config change is needed.
