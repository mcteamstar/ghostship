# Proposal

## Why

Ghostship's spec-ops image still bundles OpenSpec 1.14.3 while the Academy skills and agent prompts describe the 1.x command workflow. New crews therefore inherit stale OpenSpec guidance even though maintainers have moved to the v2 skills-only workflow.

## What Changes

- Upgrade the bundled OpenSpec CLI and its coupled generated Academy skills to the selected v2 release.
- Update Ghostship agent prompts and documentation to use backend-supported OpenSpec skill invocation and explain the `continue` fallback.
- Verify fresh crews discover the skills and can work with existing OpenSpec change artifacts; review migration output before applying changes to existing files.
- Update the dependency inventory and review evidence for the coupled CLI and skills.

## Capabilities

### New Capabilities

- `crew-openspec-workflows`: OpenSpec CLI and shared workflow-skill delivery and use in Ghostship crews.

### Modified Capabilities

- `agent-personas`: update persona guidance to invoke v2 skills while preserving the established workflow ownership split.

## Impact

The spec-ops container build, Academy's six OpenSpec skills, the Ghost/Spectre/Banshee/Wraith/Reaper persona prompts, Academy skill documentation, dependency inventory and review evidence, and fresh-crew verification. Executor-owned wrappers and its global CLI migration remain out of scope.
