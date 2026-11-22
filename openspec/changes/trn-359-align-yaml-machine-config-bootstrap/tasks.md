# Tasks

## 1. Align installer bootstrap with resolved configuration

- [x] 1.1 Move Podman setup and socket/data-directory selection from `bin/install.sh` into `install_main.py` after YAML resolution, and verify `tests/unit/test_install.py` and `tests/unit/test_podman_setup.py` pass.
- [x] 1.2 Add regression cases for repository YAML, XDG config, explicit `--config` precedence, conflicting ambient machine variables, and consistency between the selected machine, socket, data directory, and generated Compose settings; verify with `pytest tests/unit/test_install.py tests/unit/test_podman_setup.py tests/unit/test_yaml_config.py`.
- [x] 1.3 Clarify in `docs/configuration.md` that machine settings use the resolved YAML precedence before provisioning and identify the XDG environment variables that only select config/data/runtime paths; verify the documented precedence matches the installer behavior contract.
