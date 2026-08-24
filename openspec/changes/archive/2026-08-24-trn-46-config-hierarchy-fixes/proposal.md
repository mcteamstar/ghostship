## Why

`install.sh` resolves most config variables with bash's `${VAR:-default}` pattern applied *after* `--config` file sourcing. This silently absorbs whatever happens to be exported in the invoking shell as a configuration input — undocumented, inconsistent (`PORT` is the sole exception, since it's assigned a literal default *before* config sourcing), and architecturally wrong: the shell that invokes `install.sh` is not necessarily the host the transport ends up running on (see `docs/remote.md`), an exported value isn't persisted anywhere so it silently stops applying the next time `install.sh` runs unless re-exported, and it doesn't correspond to the transport container's actual runtime environment anyway (that's a separate, later step where already-resolved shell variables get baked into `podman run -e` flags). Verified empirically: when both an ambient env var and a config-file value are set for the same variable, the config file always wins — backwards from the resolution order most CLI tools use (flag > env > config > default), and backwards from what an operator reaching for an env var override would expect.

`uninstall.sh` inherited the identical gap when `--config`/`GA_MACHINE_NAME` support was added to it during the trn-42 podman-targeting bugfix earlier on this branch. The live `installation` spec is also stale: it still documents the dedicated-machine default as `ghostship`, not `ghost-academy` (renamed on this branch).

## What Changes

- Remove ambient environment-variable reading from `install.sh` and `uninstall.sh` entirely. Every config variable gets an explicit literal default assigned *before* `--config` file sourcing (mirroring `PORT`'s existing correct pattern), so an exported shell variable can no longer leak in as an unintended fourth input.
- Resulting resolution order for every variable, uniformly: **built-in default → `--config` file → CLI flag** (for the subset of variables that have one). No ambient-env tier. **BREAKING** for anyone currently relying on exporting a variable instead of using `--config` or a flag — there is no deprecation window since this was never a documented, supported input.
- Not every config field gets a flag, and a flag is not required to mirror a config field 1:1 — `--public-url` already collapses two fields (`GA_FILE_PUBLIC_URL`/`GA_MCP_PUBLIC_URL`) into one composite concept (`GA_HOST_URL`). This change doesn't add new flags for the infra-tuning knobs (`GA_MAX_CREWS`, `GA_IDLE_TIMEOUT_SECS`, the dedicated-machine block, memory-gate thresholds, subagent timeouts) — those remain config-file-only, as today.
- Fix the stale `installation` spec / `docs/configuration.md` / `config/ghostship.conf.example` references to the dedicated-machine default name (`ghostship` → `ghost-academy`).
- Sync the `installation` spec to reflect the podman-command-targeting consolidation already implemented in earlier commits on this branch: the image pull, all three `podman build` calls, the network create, the secret create, the transport `run`, and the failure-path `logs` tail now all resolve a single `_PODMAN_CMD` and target the same dedicated-instance connection when `GA_DEDICATED_MACHINE=true` — previously the pull/build/log-tail steps used bare `podman` and silently targeted the wrong (or no) instance. No further code change needed for this bullet; it's a spec-sync-only item so the live spec stops being wrong about current behavior.
- Full `docs/configuration.md` uplift: state the three-tier resolution order explicitly and prominently, correct the framing of the "Environment variables read by the transport server" table (these are `install.sh`-resolved values baked into the container's own env at `podman run` time — not something an operator sets in their own shell on any host), and make clear which variables have a corresponding flag versus config-file-only. Related install docs (`README.md`'s install section, `docs/manual-install.md`, `docs/auth.md`'s identity-provider resolution order) get a consistency pass so none of them imply ambient env vars are a supported input.
- Update `tests/test_install_config.sh` and `tests/test_dedicated_transport.sh`, which currently assert the old ambient-env-honoring behavior via self-contained duplicated logic; add a case proving an ambient env var is ignored when neither config nor flag sets it.

Explicitly out of scope: the transport container's own runtime environment variables (the `-e "VAR=..."` flags baked into `podman run`, and everything `transport/server.py` reads from its own process environment). Those remain standard, correct container configuration — this change is only about `install.sh`/`uninstall.sh` not implicitly absorbing the *invoking shell's* ambient environment as a hidden config input.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `config-file`: resolution order changes from "config file → flags → defaults" (silent on ambient env) to an explicit three-tier "default → config file → flag" with a new requirement that ambient environment variables are not read as configuration; documentation requirements updated to state this explicitly.
- `installation`: dedicated-machine default name corrected from `ghostship` to `ghost-academy`; add a requirement that `uninstall.sh`'s dedicated-machine detection honours `--config`/the same resolution order as `install.sh`, not a hardcoded name; add a requirement (spec-sync only, already implemented) that every Podman command install.sh issues under `GA_DEDICATED_MACHINE=true` targets the same resolved dedicated-instance connection.

## Impact

- `install.sh`: every config-variable default assignment moves before `--config` sourcing (mirroring `PORT`).
- `uninstall.sh`: `GA_MACHINE_NAME` default assignment moves before `--config` sourcing, closing the same leak.
- `docs/configuration.md`: resolution-order section rewritten; variable table reframed; supported-variables/flag table corrected.
- `docs/manual-install.md`, `README.md`, `docs/auth.md`: consistency pass, no behavior change.
- `config/ghostship.conf.example`: no functional change (already correct), verified consistent with the corrected docs.
- `openspec/specs/config-file/spec.md`, `openspec/specs/installation/spec.md`: delta specs per above, including the podman-command-targeting scenario (spec-sync only, no further code change).
- `tests/test_install_config.sh`, `tests/test_dedicated_transport.sh`: new/updated assertions for the no-ambient-env behavior and the corrected default name.
