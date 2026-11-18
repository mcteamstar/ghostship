# Dependency review — OpenSpec 2.1.0 — 2026-11-18

## Scope and outcome

Reviewed OpenSpec 2.1.0 as the candidate for the bundled spec-ops CLI and its
six Academy workflow skills. The CLI and its generated skill set must move as a
pair. The migration was inspected in a disposable fixture before any Academy,
image, or dependency-inventory edits. The dry run was not applied to the Ghostship
repository or to any crew project.

This review establishes the CLI package version and inspects the generated
migration and skill content. It does not establish built-image or live backend
compatibility; those checks are recorded separately below as they are attempted.

## CLI and fixture provenance

The spec-ops Containerfile currently pins `@fission-ai/openspec@1.14.3`. The
npm registry returned exactly `2.1.0` for the requested candidate. The package
was installed under `/tmp/openspec-v2-1-0-review`; its CLI reported `2.1.0`.
The environment used Node.js `v24.22.3` and npm `11.19.1`.

A disposable fixture at
`/tmp/ghostship-openspec-v2-review.Do3biZ` was initialized with the installed
1.14.3 CLI for Codex and Claude Code, then given a copy of this change's
existing OpenSpec artifacts. The copy matched the source tree byte-for-byte
(`diff -qr` returned 0). The v1 fixture setup reported six skills and six command files across `.agents` and
`.claude`, skipped commands for Codex because it uses skills, and initialized
`openspec/config.yaml` with the `spec-driven` schema.

OpenSpec 2.1.0's `openspec update --dry-run` was run against that explicit
fixture path. It reported the following complete plan:

```text
26 file(s) would change:
  update  .agents/skills/.openspec-target  (openspec)
  update  .agents/skills/openspec-apply-change/SKILL.md  (openspec)
  update  .agents/skills/openspec-archive-change/SKILL.md  (openspec)
  update  .agents/skills/openspec-explore/SKILL.md  (openspec)
  update  .agents/skills/openspec-propose/SKILL.md  (openspec)
  update  .agents/skills/openspec-sync-specs/SKILL.md  (openspec)
  update  .agents/skills/openspec-update-change/SKILL.md  (openspec)
  delete  .claude/commands/opsx/apply.md  (claude)
  delete  .claude/commands/opsx/archive.md  (claude)
  delete  .claude/commands/opsx/explore.md  (claude)
  delete  .claude/commands/opsx/propose.md  (claude)
  delete  .claude/commands/opsx/sync.md  (claude)
  delete  .claude/commands/opsx/update.md  (claude)
  add     .claude/skills/openspec-apply-change  (claude)
  delete  .claude/skills/openspec-apply-change/SKILL.md  (claude)
  add     .claude/skills/openspec-archive-change  (claude)
  delete  .claude/skills/openspec-archive-change/SKILL.md  (claude)
  add     .claude/skills/openspec-explore  (claude)
  delete  .claude/skills/openspec-explore/SKILL.md  (claude)
  add     .claude/skills/openspec-propose  (claude)
  delete  .claude/skills/openspec-propose/SKILL.md  (claude)
  add     .claude/skills/openspec-sync-specs  (claude)
  delete  .claude/skills/openspec-sync-specs/SKILL.md  (claude)
  add     .claude/skills/openspec-update-change  (claude)
  delete  .claude/skills/openspec-update-change/SKILL.md  (claude)
  update  ~/.config/openspec/config.json  (openspec)

Note: Update will also refresh the OpenSpec skills installed for this machine in ~/.agents/skills.
```

The plan replaces the generated skills, removes the old Claude command files,
replaces Claude's old generated skill copies, updates global OpenSpec
configuration, and warns that global skills will also be refreshed. No v2
migration was applied to the real repository or machine-wide skills. After the
dry run, the repository remained clean and the fixture's copied change still
matched the source.

## Skill and persona comparison before replacement

The v2.1.0 package API generated these core skills in the fixture, with
`metadata.generatedBy: "2.1.0"`:

| Workflow | Skill directory | v1 Academy generator metadata | v2 candidate metadata |
| --- | --- | --- | --- |
| explore | `openspec-explore` | 1.14.3 | 2.1.0 |
| propose | `openspec-propose` | 1.14.3 | 2.1.0 |
| update | `openspec-update-change` | 1.14.3 | 2.1.0 |
| apply | `openspec-apply-change` | 1.14.3 | 2.1.0 |
| sync | `openspec-sync-specs` | 1.14.3 | 2.1.0 |
| archive | `openspec-archive-change` | 1.14.3 | 2.1.0 |

All six checked-in Academy files match the installed 1.14.3 package templates;
no Ghostship-specific rules are embedded in those generated bodies. The v2
candidate retains the same six names, descriptions, `Bash(openspec:*)` grant,
license, compatibility, and skill metadata version. Its workflow text is updated
by upstream: v1 conditional command sections are removed and v2 CLI-instructions
fallbacks are used where applicable. The core set does not include the optional
`openspec-continue-change` skill.

One Ghostship-specific adaptation is required before replacing the generated
files. OpenSpec 2.1.0 still includes several command-file examples for other
deliveries (in explore, apply, update, sync, and archive).
Ghostship stages skills and does not promise those generated command files.
The Academy generator must rewrite those examples to neutral `openspec-*` skill
references. Persona prompts and maintained docs must show Codex's
`$openspec-*` syntax and `/openspec-*` only for the slash-skill backends. The
existing role policy remains in the persona prompts: Ghost owns all six core
workflows; Spectre owns explore/propose/update; Banshee owns
explore/propose/update/apply and hands close-out to Reaper; Reaper owns
sync/archive; Wraith may only explore OpenSpec context. If continue is needed
without `openspec-continue-change`, the guidance will use `openspec status` and
`openspec instructions` for the next ready artifact.

`AcademyLoader._stage_skills()` stages the Academy directories under
`/home/kirocrew/.agents/skills/`, after which the baked `.agents/setup` wires
them to each detected backend. The launch-time `_seed_openspec_store()` targets
the shared workspace root, which is a sibling of delivered `repo/`; it does not
run `openspec update` against a delivered project.

## Verification status

OpenSpec 2.1.0 read the existing `trn-326-upgrade-ghostship-openspec-v2`
change through the registered `repo` store. The optional continue fallback was
also exercised against `trn-328-portal-trust-boundary`: `status` reported `design`
as ready, then `instructions design` returned the design requirements and
template. No continue skill was needed. The launch seeder targets the shared
workspace root and documents `repo/` as a sibling; it does not run update against
the delivered project. No repository files changed during the disposable
migration dry run. The built-image version check was not run: `podman`, `docker`, `buildah`, and
`nerdctl` are unavailable, so no spec-ops image could be built or queried with
`openspec --version`. The standalone installed package reports `2.1.0`, and the
Containerfile pin is exact, but that does not substitute for an image check.
Fresh crew launches for the supported backends and in-crew use of the existing
change remain unverified for the same reason.

## Upstream references

- [OpenSpec 2.1.0 release notes](https://github.com/Fission-AI/OpenSpec/releases/tag/v2.1.0)
- [OpenSpec 2.0 upgrade guide](https://openspec.dev/docs/upgrade-2)
- [OpenSpec 2.1 upgrade guide](https://openspec.dev/docs/upgrade-2-1)
- [OpenSpec 2.1 supported tools](https://github.com/Fission-AI/OpenSpec/blob/v2.1.0/docs/supported-tools.md)
