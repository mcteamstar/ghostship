# Design

## Context

Enabling a backend today touches four places: the Containerfile (install steps behind an `INCLUDE_*` arg), `install.sh` (translating a config flag into that arg, and writing the flag into the compose environment), the transport's config, and the transport's login gates. Each backend has its own flag, nothing ties the flags to the backend selection, and the Claude and Codex login routes only work when their backend is the default. The consolidation makes one list the source of truth and reduces a new backend's build work to one toolchain script.

## Goals / Non-Goals

**Goals**
- One list, `GA_AGENT_BACKENDS`, decides what is built, what the transport accepts, and which logins are available.
- A new backend's toolchain needs no edit to the Containerfile or `install.sh`.
- Retired `GA_INCLUDE_*` variables fail loudly, so a stale config can't look enabled while doing nothing.

**Non-Goals**
- Per-session or per-crew backend selection (a later change).
- The `AgentBackend` interface refactor, and consolidating the login handlers and pending-login state (a later change).
- An approval deadline for kiro and Codex logins (moves with the login consolidation).
- Renaming routes, auth files, or KiroCrew-named settings.

## Decisions

### D1. The same parsing rules on both sides

The transport (`transport/config.py`) and `install.sh` each parse `GA_AGENT_BACKENDS`, so they must apply the same rules: split on commas, trim, lowercase, drop empty entries and duplicates, and always include kiro. They validate differently. The transport checks against its known backends (`kiro`, `claude`, `codex`). `install.sh` checks against `kiro` plus the scripts in `crews/spec-ops/toolchains/`, so it never holds a backend list of its own.

The shell parser lives in one sourceable file, `scripts/lib/agent_backends.sh`, which `install.sh` and the tests both source, so the tests exercise the real shell parser rather than a copy. Names must match `^[a-z][a-z0-9-]*$` and are compared against script basenames, so a path-like name can't select a script outside `toolchains/`.

A parity test checks two things: both parsers give the same normalised list (first-listed order, kiro omitted) for a shared set of inputs, and the transport's optional backends match the toolchain scripts present.

### D2. Kiro is always present, so it is never a build arg

KiroCrew bundles kiro in every image. The enabled set always contains kiro, and `AGENT_TOOLCHAINS` carries only the optional backends. Listing `kiro` is accepted and has no effect.

### D3. The default selector stays in `GA_CREW_ACP_BACKEND`

`GA_AGENT_BACKENDS` answers "what is available". `GA_CREW_ACP_BACKEND` answers "what is used when nothing else says". Keeping both leaves the crew config path unchanged in this change, and leaves room for per-session selection later. A single ordered list whose first entry is the default was rejected, because reordering the list would silently change behaviour.

### D4. One list drives per-backend toolchain scripts

`install.sh` passes one build arg, `AGENT_TOOLCHAINS` (for example `claude,codex`). The Containerfile copies `crews/spec-ops/toolchains/` and runs one loop that executes `<name>.sh` for each entry, with `set -e` so a failing script fails the build and is named in the output. Each script owns its pinned versions. Adding a backend's toolchain means adding a script; the Containerfile and `install.sh` don't change.

Per-backend `INCLUDE_*` build args were rejected, because they keep a Containerfile block per backend.

The image records its list in the `org.ghostship.toolchains` label. `install.sh` already forces a cache-less build when the baked version label is stale, because podman can reuse a cached layer when only a build arg changes. It applies the same check to the toolchain label, so adding a backend at the same version can't reuse a stale layer.

### D5. Retired flags fail, no aliases

Dev phase, so there are no aliases. If `GA_INCLUDE_CLAUDE_AGENT` or `GA_INCLUDE_CODEX_AGENT` is present with a non-empty value, the transport and `install.sh` fail with a message naming `GA_AGENT_BACKENDS`. Silently ignoring them was rejected: an operator who sets `GA_INCLUDE_CLAUDE_AGENT=true` would believe Claude is enabled while nothing changed.

The generated compose file currently writes both variables into the transport environment, defaulting to `"false"`. Removing those entries must land in the same step as the transport's rejection, or every startup fails.

### D6. Login follows the set, not the default

The Claude and Codex login routes currently check that their backend is the default. That conflicts with the set model, and it would stop an operator from logging in to Claude while kiro is the default. The routes check membership in the enabled set instead. Logout is not gated, so stored credentials can always be removed, even after a backend is disabled.

The launch path keeps a guard that refuses a backend outside the set (`backend_not_enabled`). Configuration can't reach it in this change, because startup already rejects a default outside the set, so no requirement covers it and it is tested only by patching. It is kept as a defensive check, and becomes a requirement once per-session selection lands.

`POST /login/claude/code` runs the membership check before parsing the body or looking up the pending flow, matching where the backend check sits today.

### D7. Hard failures and warnings

Three conditions stop startup: an unknown backend name, a default backend outside the set, and a retired flag. Each names the settings involved and the `ghostship install` re-run. Settings for a disabled backend only warn: failing would turn a harmless leftover into an outage. Warnings name the setting, never its value, because the settings include API keys.

Where each check runs matters, because `Config.from_env()` is called at import time in eight modules. Parsing and the three hard failures run in `from_env()`, so every module sees the same validated config and a bad value fails on first import. They do not go in `__post_init__`, which would break tests that build a `Config` directly. The inert-setting warnings need `DATA_DIR` reads, which `Config` doesn't do, and would repeat eight times from `from_env()`. They run once, from the transport's startup path in `server.py`.

`install.sh` repeats the default-backend check before building, so a bad pair of settings fails in seconds rather than after a full build and a `restart: always` loop.

### D8. Boundaries this change leaves in place

- **Enabled but not the default.** A backend can be enabled without being the default. Its credentials and base URL are then accepted and not warned about, but no crew uses them, because injection still follows the default. That is intended until per-session selection, which is what will use them.
- **Existing crews.** A crew registered on a backend that is later disabled keeps its image and config. Restarting it starts the existing container with no check. Disabling a backend affects new crews and new logins only.
- **`--client-only` installs.** The retired-flag check applies in every mode, since it is a config error. The toolchain, name and default-backend checks are skipped, because client-only mode builds nothing and runs no transport.

## Risks / Trade-offs

- **Two parsers can drift.** Mitigated by the parity test in D1.
- **Config edits without a reinstall.** The image and the transport environment are both written by `install.sh`, so editing `ghostship.conf` and running `ghostship start` changes neither. An operator who adds `claude` and restarts sees Claude refused. Mitigated by every error naming the `ghostship install` re-run. A later change could have the transport compare the image's `org.ghostship.toolchains` label with its own set at startup.
- **Misleading scenario names.** The pin scenarios are still called "Pinned … in Containerfile" but now read the toolchain scripts. The names must be kept for the archive to apply; a later spec cleanup can rename them.
- **The list-driven build changes the Containerfile shape.** A failing toolchain script must fail the build visibly. Mitigated by `set -e` and a build check with every toolchain enabled.
- **A stale `GA_INCLUDE_*` stops the transport.** This is intentional, and the message names the replacement.

## Migration Plan

1. Archive `trn-202-claude-backend-fixes`, since this change modifies its opt-in requirement.
2. Land parsing, validation and the inert warnings, with tests.
3. Land the retired-flag rejection in the same step as removing the `GA_INCLUDE_*` compose entries and `install.sh` defaults (D5).
4. Land login gating by membership and the renamed launch guard.
5. Land the toolchain scripts and the Containerfile loop.
6. Migrate `config/ghostship.conf` on this machine to `GA_AGENT_BACKENDS=claude` and re-run `ghostship install`. Startup fails until this is done.
7. Verify: build with every toolchain, launch a Claude crew, and confirm Codex login is refused while codex is disabled.
