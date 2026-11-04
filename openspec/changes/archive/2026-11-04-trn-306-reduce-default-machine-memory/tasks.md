# Tasks

## 1. Update default values in source

- [x] 1.1 `bin/install.sh`: change `GA_MACHINE_MEMORY:-16384` to `GA_MACHINE_MEMORY:-8192` and verify `bash -n bin/install.sh` passes
- [x] 1.2 `bin/lib/podman_setup.py`: change dataclass field `machine_memory: int = 16384` to `8192` and the `env.get("GA_MACHINE_MEMORY", "16384")` fallback to `"8192"`; verify `grep 16384 bin/lib/podman_setup.py` returns no matches
- [x] 1.3 `bin/lib/install_main.py`: change `_g("GA_MACHINE_MEMORY", "16384")` fallback to `"8192"`; verify `grep 16384 bin/lib/install_main.py` returns no matches
- [x] 1.4 `bin/lib/yaml_config.py`: change `"GA_MACHINE_MEMORY": "16384"` in the defaults dict to `"8192"`; verify `grep 16384 bin/lib/yaml_config.py` returns no matches

## 2. Update configuration example and docs

- [x] 2.1 `config/ghostship.yaml.example`: change `memory_mb: 16384` to `memory_mb: 8192`; verify `grep 16384 config/ghostship.yaml.example` returns no matches
- [x] 2.2 `docs/configuration.md`: change default column value `16384` to `8192` and update prose description of `GA_MACHINE_MEMORY` to reflect 8 GB; verify `grep 16384 docs/configuration.md` returns no matches

## 3. Integration verification

- [x] 3.1 Run `grep -r "16384" bin/ config/ docs/` and verify zero matches
- [x] 3.2 Run `python -m pytest tests/unit/ -q` and verify no regressions

## Workflow follow-up

- Archive the change after implementation is verified.
