# Design

## Context

The `GA_MACHINE_MEMORY` default is defined in multiple locations that must stay in sync: the shell install script, two Python modules that parse it, the YAML config defaults map, the example config file, and the documentation. See proposal.md for motivation.

## Goals / Non-Goals

**Goals:**
- Change the numeric default from 16384 to 8192 in every active location where it is defined or documented
- Keep all locations consistent so no file reports a different default than another

**Non-Goals:**
- Migrating existing machines — this is a new-install default only
- Changing `GA_MACHINE_CPUS` or `GA_MACHINE_DISK`
- Adding any migration path or tooling

## Decisions

**Update all definition sites atomically, not one at a time.**
The default lives in five distinct files. If only some are updated the system is inconsistent: a user reading `docs/configuration.md` sees a different value than what `install.sh` uses. All six files are updated in the same PR.

**Leave archived OpenSpec specs unchanged.**
Archived specs are historical records — they document what was true when those changes landed. Retroactively editing them would misrepresent history and provide no user value.

**Leave `docs/troubleshooting.md` unchanged.**
The troubleshooting guide already uses `8192` as its example resize target (`podman machine set --memory 8192`). No change needed.

## Risks / Trade-offs

- **[Risk]** Existing `ghost-academy` machines stay at 16 GB after users upgrade — the default only applies to new installs. **Mitigation**: acceptable by design; users who want to reclaim memory can follow the `podman machine set --memory 8192` path already documented in `docs/troubleshooting.md`.
- **[Risk]** Missing one of the six definition sites leaves an inconsistency. **Mitigation**: tasks.md enumerates every file individually and includes a `grep` verification step that asserts zero remaining `16384` occurrences in the active source tree.
