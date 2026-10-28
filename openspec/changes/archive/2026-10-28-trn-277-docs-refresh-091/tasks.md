# Tasks

## 1. Fix stale port range in portal.md

- [ ] 1.1 In `docs/portal.md` line 47, replace `64058–65081` with `64058–64121`; verify by running `grep "65081" docs/portal.md` and confirming no matches remain.

## 2. Document steer() follow_up fallback in architecture.md

- [ ] 2.1 Append two sentences to the `steer()` paragraph in `docs/architecture.md` (Dispatch model section): (a) explain the `mode=follow_up` fallback when the gateway returns `steer_unsupported` on claude/codex backends and that the response carries `action: "follow_up_queued"`; (b) note that `503 session_starting` means the task hasn't started yet and to retry rather than use `force=True`. Verify by reading the updated paragraph and confirming the two new behaviours are described.

## 3. Add profileArn troubleshooting section to troubleshooting.md

- [ ] 3.1 Add a new H2 section `## "profileArn is required for this request"` after the `## Bootstrap crash` section in `docs/troubleshooting.md`. The section must cover both causes: (a) stale kiro credential — fix with `ghostship auth logout kiro` then `ghostship auth login kiro`; (b) wrong model-ID spelling (`claude-haiku-5-5` vs `claude-haiku-5.5`) — fix by updating the model ID and re-running `./install.sh`. Verify by reading the section and confirming both causes and fixes are present.

## 4. Add v0.9.0 and v0.9.1 release links to README

- [ ] 4.1 In `README.md`, immediately after the existing `[docs/release-notes-0.8.1.md]` bullet in the resource list, add two new bullets linking to the v0.9.0 and v0.9.1 CHANGELOG anchor sections (`CHANGELOG.md#v090` and `CHANGELOG.md#v091`). Verify by reading the updated resource list and confirming both new entries are present alongside the existing v0.8.1 entry.

## 5. Commit

- [ ] 5.1 Stage and commit all four changed files (`docs/portal.md`, `docs/architecture.md`, `docs/troubleshooting.md`, `README.md`) with a commit message summarising the v0.9.1 docs refresh. Verify with `git log --oneline -1` that the commit is recorded.

## Workflow follow-up

- After review, archive the change with `openspec archive trn-277-docs-refresh-091`.
