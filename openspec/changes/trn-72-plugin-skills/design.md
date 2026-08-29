# TRN-72 Design — Plugin Skill Improvements

## D1: Three-skill taxonomy

Ghostship's plugin ships three skills with distinct, non-overlapping scopes:

| Skill | Scope | Audience |
|:------|:------|:---------|
| `ghostship-admin` | Host-level setup: install, auth, connect client, upgrade, tear down | The person who owns the machine ghostship runs on |
| `ghostship-command` | Fleet operations over MCP: launch, seed, dispatch, pickup, steer, captain, evac, nuke | Anyone holding the MCP connection and driving the fleet |
| `ghostship-capability` | Academy/crew configuration: agents, skills, steering, orders, MCP catalogue, compositions | Operator who wants to customise what crews can do |

The three form a clear progression: *get it running* (admin) → *configure it*
(capability) → *use it* (command). Each can be used independently — a user
connecting to a remote ghostship instance they didn't install will only ever
need command.

## D2: File locations

```
.claude-plugin/
  plugin.json                          ← skills array lists distributed skills
  skills/
    ghostship-admin/SKILL.md
    ghostship-command/SKILL.md
    ghostship-capability/SKILL.md      ← new (TRN-72)
```

Each SKILL.md carries a `version:` field in its YAML frontmatter that must
match the repo's `VERSION` file. This is enforced by the release gate before
any PR to main can merge.

## D3: Version sync mechanism

`VERSION` is the single canonical source of truth. At release time, all of
the following must match:

- `VERSION` file
- `.claude-plugin/plugin.json` → `version`
- `.claude-plugin/.claude-plugin/plugin.json` → `version`
- `.claude-plugin/skills/*/SKILL.md` → `version:` frontmatter field

The `.github/workflows/release-gate.yml` CI check validates all four. A
mismatch blocks the PR from merging into main.

## D4: `ghostship-capability` distribution decision

**Decision: include by default in `plugin.json`.**

Rationale: the skill is keyword-triggered, not always-on — it doesn't
bloat context for users who never ask about academy configuration. New
operators benefit from having it available without a separate install step.
Advanced users who don't want it can ignore it.

Implementation: add `ghostship-capability` to the `skills` array in
`.claude-plugin/plugin.json` and `.claude-plugin/.claude-plugin/plugin.json`.

## D5: Cross-references between skills (task 2.4)

After ghostship-capability is wired in, add brief cross-references:

- `ghostship-admin` — at the end of the install section, note:
  "To configure what crews can do (agents, skills, MCP servers), use
  `ghostship-capability` after installation."
- `ghostship-command` — in the MCP server / composition context, note:
  "To add new MCP servers to the catalogue or build new compositions,
  use `ghostship-capability`."

These are one-line pointers, not content duplication.

## D6: `~/.ghostship` as the persistent data home

`~/.ghostship` is established as the recommended install location for
agent-driven installs. The rationale: mirrors the pattern of `~/.kiro`,
`~/.claude`, etc. — a clean, predictable home. Future persistent data
(config cache, credentials, skill state) has a natural home here without
any further design work.

The admin skill recommends `~/.ghostship/ghostship` as the default repo
clone path. `ghostship.conf` at `~/.ghostship/ghostship.conf` (or the
default install location) is the operator config file.

## Affected files

- `.claude-plugin/skills/ghostship-admin/SKILL.md` — updated
- `.claude-plugin/skills/ghostship-command/SKILL.md` — rewritten
- `.claude-plugin/skills/ghostship-capability/SKILL.md` — created
- `.claude-plugin/plugin.json` — version bump; capability skill to be added
- `.claude-plugin/.claude-plugin/plugin.json` — same
- `VERSION` — bumped to 0.2.0
- `.github/workflows/release-gate.yml` — skill version check added
