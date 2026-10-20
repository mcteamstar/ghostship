# Tasks

## 1. Write generation script

- [x] 1.1 Create `scripts/generate-openspec-skills.js` — for each skill, call the zero-arity template getter, assemble SKILL.md frontmatter (preserving `allowed-tools` from existing file), write to `academy/skills/<skill>/SKILL.md` — verify script runs without error and produces valid SKILL.md files

## 2. Generate updated skills

- [x] 2.1 Install `@fission-ai/openspec@1.14.3` globally, run the generation script, verify all 6 SKILL.md files updated with `generatedBy: "1.14.3"` and non-empty instructions

## 3. Bump Containerfile

- [x] 3.1 Update `crews/spec-ops/Containerfile`: `@fission-ai/openspec@1.9.0` → `@1.14.3` — verify version string is correct

## 4. Verify and commit

- [x] 4.1 Reinstall `@fission-ai/openspec@1.9.0` locally (restore dev environment) — verify `openspec --version` returns `1.9.0`
- [x] 4.2 Commit Containerfile bump + all 6 regenerated SKILL.md files in one commit

## Workflow follow-up

- Deploy to starport (`ghostship upgrade`) to rebuild the spec-ops image with the new openspec version
