# Tasks: TRN-166 KiroCrew 0.7.2 upgrade

> Gate: `trn-173-seed-kiro-db-0-7-2-verification` must be merged before starting.

## 1. Bump base image

- [ ] 1.1 In `crews/_base/admission/Containerfile`, change `FROM ghcr.io/kirodotdev/kirocrew:0.6.0` to `FROM ghcr.io/kirodotdev/kirocrew:0.7.2`
- [ ] 1.2 Update the comment from "Pinned to 0.5.0 semver tag" to "Pinned to 0.7.2 semver tag"

## 2. Fix sandbox config in scripts/install.sh

- [ ] 2.1 Find the config patch that sets `"sandbox": "off"`: `grep -n "sandbox" scripts/install.sh`
- [ ] 2.2 Replace `"sandbox": "off"` with `"sandbox_allow_unsandboxed_exec": true` in the generated crew config

## 3. Set orchestrator.max_plan_duration_seconds

- [ ] 3.1 In the config patch in `scripts/install.sh`, add `"orchestrator": { "max_plan_duration_seconds": 14400 }` (or merge into an existing orchestrator block)

## 4. Add minimal_context to polling crons

- [ ] 4.1 Locate where Raven patrol and heartbeat crons are created (transport or install script)
- [ ] 4.2 Add `"minimal_context": true` to each polling/scanning cron job definition

## 5. Audit and remove KIRO_API_KEY references

- [ ] 5.1 Run `grep -rn "KIRO_API_KEY" . --include="*.py" --include="*.sh" --include="*.json"` and remove any injection of `KIRO_API_KEY` into agent or crew environment

## 6. Rebuild images and validate on academy

- [ ] 6.1 Run `./install.sh` to rebuild all crew images
- [ ] 6.2 Launch a new spec-ops crew and confirm no EPERM errors in agent boot logs
- [ ] 6.3 Run a Ghost task and confirm it completes successfully
- [ ] 6.4 Trigger a Captain check-in; confirm Raven patrol fires and produces a summary
- [ ] 6.5 Check `ghostship status` for no kiro-cli migration errors on first boot

## 7. Update docs and specs

- [ ] 7.1 Update `docs/architecture.md` base image version reference to 0.7.2
- [ ] 7.2 Update `openspec/specs/installation/spec.md` to document `sandbox_allow_unsandboxed_exec`, `max_plan_duration_seconds`, and `minimal_context` cron option

## 8. Run tests and commit

- [ ] 8.1 Run `python -m pytest tests/unit/ -x -q` and confirm all tests pass
- [ ] 8.2 Confirm `openspec validate --change trn-166-kirocrew-0-7-2-upgrade` passes
- [ ] 8.3 Commit: `chore: upgrade crew base image to KiroCrew 0.7.2`
