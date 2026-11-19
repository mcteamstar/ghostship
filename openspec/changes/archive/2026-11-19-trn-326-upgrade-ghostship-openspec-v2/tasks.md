# Tasks

## 1. Inspect OpenSpec v2 migration and skill output

- [x] 1.1 Generate OpenSpec 2.1.0 skill and migration output in a disposable fixture containing legacy generated command files and a representative existing change; record the full output and verify no real crew/project files are modified.
- [x] 1.2 Compare the generated core skill set and instructions with Ghostship's six Academy skills and persona contracts; document any required Ghostship-specific adaptation in the dependency review evidence before replacing assets.

## 2. Upgrade the bundled CLI and Academy skills

- [x] 2.1 Pin `@fission-ai/openspec` to 2.1.0 in the spec-ops image and verify a fresh Corsair spec-ops crew reports that exact CLI version.
- [x] 2.2 Refresh all six Academy OpenSpec workflow skill directories from the inspected v2 shared-skill output, preserving Ghostship-specific policy where required; verify front matter, skill names, and generated version match the CLI pin.
- [x] 2.3 Add the selected `openspec-verify-change` skill to Academy from the OpenSpec 2.1.0 verify template; verify its skill name, workflow instructions, and CLI compatibility.
- [x] 2.4 Extend regression checks to cover the six core skills and selected verify skill; verify validation fails for missing or incompatible bundled skills.

## 3. Update persona prompts and Academy documentation

- [x] 3.1 Update Ghost, Spectre, Banshee, Wraith, and Reaper prompts with their existing workflow responsibilities and backend-supported v2 skill invocation; verify no prompt claims `/opsx:*` files are available.
- [x] 3.2 Update Academy skill delivery documentation to describe shared `.agents/skills/` staging and the v2 `continue` CLI-instructions fallback; verify the documented path matches `AcademyLoader` and the bundled CLI.
- [x] 3.3 Update OpenSpec workflow examples in repository documentation for Codex `$openspec-*` and slash-skill backends `/openspec-*`; verify no v1 command-file instructions remain in the maintained Ghostship workflow docs.
- [x] 3.4 Update Academy skill delivery documentation to list `openspec-verify-change` and explain which planned workflow uses it; verify the documented skill name matches the shipped directory.

## 4. Record dependency and migration evidence

- [x] 4.1 Update `config/dependencies.yaml` for the exact OpenSpec 2.1.0 CLI pin and coupled Academy skill source; verify the inventory checker accepts the declarations and evidence path.
- [x] 4.2 Add dated dependency review evidence with the disposable migration inspection, generated skill comparison, image version check, and known backend/runtime verification limits; verify all OpenSpec inventory entries reference the new evidence.
- [x] 4.3 Add `openspec-verify-change` to the dependency inventory and record its source/version compatibility evidence; verify the inventory checker accepts the entry.

## 5. Verify upgraded fresh-crew workflow

- [x] 5.1 Launch one fresh Codex spec-ops crew and verify CLI version and discovery of all seven bundled skills; statically inspect shared `.agents/setup` delivery and supported invocation syntax for the other backends without launching a separate crew for each.
- [x] 5.2 Exercise a representative existing OpenSpec change in an upgraded crew and verify it remains readable and usable; confirm no migration is applied to real crew project files during launch.
- [x] 5.3 Verify the optional `continue` path using the bundled CLI instructions fallback when its skill is absent, and record the result with the release verification evidence.
