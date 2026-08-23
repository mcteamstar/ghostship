## 1. Transport server — env var and config patch

- [x] 1.1 Add `KC_MODEL_DEFAULT = os.environ.get("KC_MODEL_DEFAULT", "")` module-level constant in `transport/server.py` (next to existing `KC_MODEL_OVERRIDE`)
- [x] 1.2 In `_patch_crew_config`, conditionally write `a['default_model'] = KC_MODEL_DEFAULT` only when `KC_MODEL_DEFAULT` is non-empty (after the existing `subagent_max_turns` line)

## 2. install.sh — flag and pass-through

- [x] 2.1 Add `--model-default` flag to the argument parser in `install.sh`, storing the value in a `MODEL_DEFAULT` variable (empty by default)
- [x] 2.2 When `MODEL_DEFAULT` is non-empty, pass `-e KC_MODEL_DEFAULT="${MODEL_DEFAULT}"` to the `podman run` command for `ga-transport`
- [x] 2.3 Add `KC_MODEL_DEFAULT` to the config-file variable sourcing block (parallel to `KC_MODEL_OVERRIDE`)

## 3. Documentation

- [x] 3.1 Add a `KC_MODEL_DEFAULT` row to the env-var table in `docs/configuration.md` with description and default `_(unset)_`
- [x] 3.2 Add `KC_MODEL_DEFAULT` / `--model-default` to the "Supported variables" table in the Config file section of `docs/configuration.md`
- [x] 3.3 Add a commented-out `KC_MODEL_DEFAULT` line to `config/ghostship.conf.example`

## 4. Tests

- [x] 4.1 In `transport/test_transport.py`, extend the existing `_patch_crew_config` test to assert `default_model` is written when `KC_MODEL_DEFAULT` is set
- [x] 4.2 Add a test case asserting `default_model` is NOT present in the patched config when `KC_MODEL_DEFAULT` is empty/unset
