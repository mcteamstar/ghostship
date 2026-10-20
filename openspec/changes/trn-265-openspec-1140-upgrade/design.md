# Design

## Context

See proposal.md. The `skill-templates.js` module in the npm package exposes zero-arity getters for each skill's content. The SKILL.md format used by ghostship wraps the template output in YAML frontmatter.

## Goals / Non-Goals

**Goals:**
- Crew agents use the latest openspec CLI and skill instructions
- SKILL.md content matches what the installed CLI version expects

**Non-Goals:**
- Changing which skills are bundled
- Any transport or test changes

## Decisions

### D1: Generate via Node.js script, not CLI

`openspec update` requires an initialised project root and manages its own tool wiring. Direct invocation of `skill-templates.js` via a one-off Node script is simpler, reproducible, and doesn't require a temp project. A generation script can be committed to `scripts/` for future upgrades.

### D2: Preserve allowed-tools from existing files

The template API doesn't return `allowed-tools`. Each skill's existing `allowed-tools` frontmatter must be preserved verbatim — copy from the current files.

### D3: Pin to exact version in Containerfile

`@1.14.3` not `@latest` — consistent with existing pin discipline.

## Migration Plan

1. Write `scripts/generate-openspec-skills.js` — reads templates from the installed package, writes SKILL.md files
2. Run with `node scripts/generate-openspec-skills.js` (requires `@fission-ai/openspec@1.14.3` installed globally)
3. Bump Containerfile version
4. Commit both together
5. Rebuild crew image on next `ghostship upgrade`
