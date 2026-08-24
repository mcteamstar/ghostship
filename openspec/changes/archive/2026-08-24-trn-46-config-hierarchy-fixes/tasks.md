## 1. `install.sh` — close the ambient-env leak, tier by tier

- [x] 1.1 Move `GA_FILE_PUBLIC_URL`/`GA_MCP_PUBLIC_URL` literal defaults (currently `"${VAR:-}"` in the flag-parsing preamble) to before `--config` sourcing.
- [x] 1.2 Add literal `""` defaults, before `--config` sourcing, for the flagged vars that currently have none at all: `KIRO_IDENTITY_PROVIDER`, `KIRO_REGION`, `KIRO_LICENSE`, `KC_MODEL_OVERRIDE`, `KC_MODEL_DEFAULT`, `GA_HOST_URL`.
- [x] 1.3 Add a literal `""` default for `GA_API_KEY` before `--config` sourcing. Verify this doesn't change the existing persisted-file behavior (`API_KEY_PROJECTION`) — a config-file-set key and a `--api-key`-flag-set key must still both work exactly as today; only an ambient-env-only value (no flag, no config) should stop silently enabling API-key auth.
- [x] 1.4 Move the five dedicated-machine literal defaults (`GA_DEDICATED_MACHINE`, `GA_MACHINE_CPUS`, `GA_MACHINE_MEMORY`, `GA_MACHINE_DISK`, `GA_MACHINE_NAME`) from after `--config` sourcing to before it (same values, same defaults — `ghost-academy` for the name).
- [x] 1.5 Add literal defaults, before `--config` sourcing, for the vars that currently only get a default at the `-e` line in the transport `run` command: `GA_MAX_CREWS`, `GA_MAX_ACTIVE_CREWS`, `GA_IDLE_TIMEOUT_SECS`, `GA_FILE_TTL_SECS`, `GA_SUBAGENT_TIMEOUT_SECS`, `GA_SUBAGENT_MAX_TURNS`, `GA_PICKUP_MAX_POLL_SECS`, `KC_GATEWAY_TOKEN_TTL`, `GA_MIN_FREE_MEM_GB`, `GA_MEMORY_WAIT_SECS`, `GA_SPAWN_MIN_MEMORY_GB`, `GA_RESOURCE_PRESSURE_GB`, `GA_RESOURCE_CRITICAL_GB`, `HOST`.
- [x] 1.6 Confirm the `-e "VAR=${VAR:-default}"` lines in the transport `run` command are unchanged (they reference the script's own already-resolved local variable at that point, not ambient env — see design.md).
- [x] 1.7 Re-read the full resulting variable-resolution section top to bottom and confirm every name from `grep -oE '\$\{?[A-Z_][A-Z0-9_]*\b' install.sh` that is a genuine config input (not an internal/derived var like `DATA_DIR`, `GHOSTSHIP_DIR`, `PODMAN_SOCK`, `_PODMAN_CMD`) now has a pre-config literal default.

## 2. `uninstall.sh` — same fix

- [x] 2.1 Move `_MACHINE_NAME="${GA_MACHINE_NAME:-ghost-academy}"` to a literal `GA_MACHINE_NAME=ghost-academy` default assignment before `--config` sourcing, then `_MACHINE_NAME="$GA_MACHINE_NAME"` after.

## 3. Specs sync

- [x] 3.1 Confirm the `config-file` and `installation` delta specs in this change directory match the final implementation (variable list, default values, resolution-order wording).
- [x] 3.2 Verify (no code change expected — already implemented in earlier commits on this branch) that `install.sh`'s image pull, all three `podman build` calls, the network create, the secret create, the transport `run`, and the failure-path `logs` tail all resolve and use the same `_PODMAN_CMD` under `GA_DEDICATED_MACHINE=true`, matching the new "Every Podman command targets the dedicated instance" scenario in the `installation` spec delta.

## 4. Docs uplift

- [x] 4.1 Rewrite `docs/configuration.md`'s resolution-order explanation: state built-in default → config file → flag prominently near the top of the "Config file" section, explicitly note there is no ambient-environment-variable tier, and add a short callout that this is a behavior change from any prior reliance on exported shell variables.
- [x] 4.2 Reframe `docs/configuration.md`'s "Environment variables read by the transport server" table intro to clarify these are `install.sh`-resolved values baked into the container's own runtime environment at `podman run` time — not variables an operator sets by exporting them in any shell (installer's or otherwise).
- [x] 4.3 Verify the "Supported variables" (flag-mapped) table is still accurate and add a sentence pointing out that variables outside that table are config-file-only, no flag, no env var.
- [x] 4.4 Check `docs/manual-install.md` for any language implying env vars are a supported install-time input; correct if so.
- [x] 4.5 Check `README.md`'s install section for the same; correct if so.
- [x] 4.6 Check `docs/auth.md`'s identity-provider resolution-order section for the same; correct if so (it should already read config file → flags → interactive prompt, per the existing `config-file` spec's auth-docs requirement — just verify no env-var wording crept in).

## 5. Test coverage

- [x] 5.1 In `tests/test_install_config.sh`, add cases proving an ambient env var is ignored when neither `--config` nor a flag sets it, for one variable from each category: a flagged var (e.g. `PORT` or `KIRO_IDENTITY_PROVIDER`), a dedicated-machine var (`GA_MACHINE_NAME`), and a memory-gate/crew-limit var (e.g. `GA_MAX_CREWS`).
- [x] 5.2 In the same file, add a case proving a config-file value still overrides an ambient env var for at least one of the above (guards against a future regression back to the old, backwards precedence).
- [x] 5.3 Update `tests/test_dedicated_transport.sh`'s socket-path-resolution mocks to match if their local reimplementation of the resolution logic needs the same no-ambient-env behavior reflected.
- [x] 5.4 Run `bash tests/test_install_config.sh` and `bash tests/test_dedicated_transport.sh`; confirm the pre-existing unrelated `curl`/socat flake in the latter is the only failure, if any.

## 6. Verification

- [x] 6.1 Real end-to-end check: export an ambient env var for one config-file-only variable (e.g. `GA_MACHINE_NAME`) with no `--config` and no flag, run `install.sh`, and confirm the built-in default took effect, not the ambient value.
- [x] 6.2 Real end-to-end check: repeat with a `--config` file also setting that variable to a third value, confirm the config-file value wins.
- [x] 6.3 `openspec validate --strict trn-46-config-hierarchy-fixes` passes.
