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
  plugin.json                          ← plugin metadata and version
  skills/
    EXTERNAL_SKILLS.md                 ← index of consumer-facing skills
    ghostship-admin/SKILL.md
    ghostship-command/SKILL.md
    ghostship-capability/SKILL.md      ← new (TRN-72)
```

Skills are auto-discovered by the harness from the `skills/` directory —
no explicit skills array in `plugin.json` is required. `EXTERNAL_SKILLS.md`
is the human-readable index that documents what each skill covers.

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

## D4: `ghostship-capability` distribution

**Decision: include by default — auto-discovered alongside the other two skills.**

Skills are discovered automatically from the `skills/` directory — no
explicit registration needed. `ghostship-capability` is available to any
agent that has the plugin installed, just like `ghostship-admin` and
`ghostship-command`. It's keyword-triggered, not always-on, so it doesn't
bloat context for users who never ask about academy configuration.

`EXTERNAL_SKILLS.md` is updated to index all three skills with scope
summaries.

## D5: Cross-references between skills

Brief one-line pointers added to each skill:

- `ghostship-admin` — end of the "Beyond the common path" section points to
  `ghostship-capability` for post-install academy customisation.
- `ghostship-command` — opening paragraph points to `ghostship-capability`
  for MCP server wiring and composition building.

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
- `.claude-plugin/skills/EXTERNAL_SKILLS.md` — updated to index all three skills
- `.claude-plugin/plugin.json` — version bump to 0.2.0
- `.claude-plugin/.claude-plugin/plugin.json` — version bump to 0.2.0
- `VERSION` — bumped to 0.2.0
- `README.md` — three-skill mentions in quick install and plugin sections
- `.github/workflows/release-gate.yml` — skill version check added
