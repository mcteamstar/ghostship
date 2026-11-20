# Tasks

## 1. Relocate inventory and defaults

- [x] 1.1 Move `config/dependencies.yaml` to root `dependencies.yaml` without changing inventory data, and verify the moved file is byte-identical to the original.
- [x] 1.2 Update both checker defaults to resolve `dependencies.yaml` from the selected repository root, and verify `validate` works with the default path and with `--root`.
- [x] 1.3 Update default-path unit coverage while preserving explicit `--inventory` override and fixture-path coverage; run the dependency checker unit tests.

## 2. Update current documentation

- [x] 2.1 Update README, dependency guide, and release checklist links/instructions to point to root `dependencies.yaml`, then verify each link and command reference.
- [x] 2.2 Search maintained files for stale production references to `config/dependencies.yaml`, confirm remaining historical/fixture references are intentional, and run `python3 scripts/dependency_check.py validate`.
