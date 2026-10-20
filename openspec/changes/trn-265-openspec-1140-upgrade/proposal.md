# Proposal

## Why

The spec-ops crew image bundles `@fission-ai/openspec@1.9.0` and all six `openspec-*` SKILL.md files were generated from that version. The current release is `1.14.3` — five minor versions newer with updated workflow instructions across all skills.

## What Changes

- Bump `crews/spec-ops/Containerfile`: `@fission-ai/openspec@1.9.0` → `@1.14.3`
- Regenerate all six SKILL.md files from the 1.14.3 template API and update `metadata.generatedBy` to `1.14.3`:
  - `academy/skills/openspec-explore/SKILL.md`
  - `academy/skills/openspec-propose/SKILL.md`
  - `academy/skills/openspec-update-change/SKILL.md`
  - `academy/skills/openspec-apply-change/SKILL.md`
  - `academy/skills/openspec-sync-specs/SKILL.md`
  - `academy/skills/openspec-archive-change/SKILL.md`

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
<!-- No spec-level behaviour changes — this is a tooling/content update. skip_specs: true set in .openspec.yaml. -->

## Impact

- `crews/spec-ops/Containerfile` — version pin only
- `academy/skills/openspec-*/SKILL.md` — regenerated content (all 6 changed)
- No transport, API, or test changes

## Research notes

Generation approach confirmed: `@fission-ai/openspec@1.14.3` exposes templates via `dist/core/templates/skill-templates.js`. Each skill has a zero-arity getter:

| Skill | Function |
|:------|:---------|
| openspec-explore | `getExploreSkillTemplate()` |
| openspec-propose | `getOpsxProposeSkillTemplate()` |
| openspec-update-change | `getUpdateChangeSkillTemplate()` |
| openspec-apply-change | `getApplyChangeSkillTemplate()` |
| openspec-sync-specs | `getSyncSpecsSkillTemplate()` |
| openspec-archive-change | `getArchiveChangeSkillTemplate()` |

Each returns `{ name, description, instructions, metadata: { author, version } }`. The SKILL.md frontmatter is hand-assembled from these fields. `allowed-tools` is not returned by the template and must be preserved from the existing files. All 6 skills have changed content between 1.9.0 and 1.14.3 — notable updates include revised command name references (`/opsx:*` style) and workflow instruction updates.
