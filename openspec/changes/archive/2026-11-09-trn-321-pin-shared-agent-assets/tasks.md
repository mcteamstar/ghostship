# Tasks

> Historical completion record: commit `9ca4735e` subsequently restored `main` as the default and removed the moving-ref warning. The baked commit is recorded inside the image; the image label records the requested ref.

## 1. Pin the image

- [x] 1.1 Change `crews/spec-ops/Containerfile` to fetch `AGENTS_REF` by commit with `git init`/`git fetch --depth 1`/`git checkout FETCH_HEAD`, default `AGENTS_REF` to `3ca5a8822a9622012a7cad9a2383e88e7919ab1d`, write the resolved SHA into the image, and correct the comment; verify with `ghostship install` and `podman image inspect localhost/spec-ops:latest` showing the SHA label.
- [x] 1.2 Confirm a branch override still builds by setting `machine.images.agents_ref: main` in a scratch config and running the image build; the build succeeds.
- [x] 1.3 Add an installer warning in `bin/lib/install_main.py` when `AGENTS_REF` is not a 40-character SHA or a `v*` tag; verify with a unit test.

## 2. Inventory

- [x] 2.1 Update `config/dependencies.yaml` `shared-agent-assets` to record the pinned SHA and an exact-commit version policy; `python3 scripts/dependency_check.py validate` passes.
- [x] 2.2 Make `scripts/dependency_check.py` report the entry as unpinned when the Containerfile default is not a SHA; verify with a fixture test in `tests/unit/test_dependency_check.py`.
- [x] 2.3 Update `docs/dependencies.md` with how to bump the pin.

## 3. Verification

- [x] 3.1 Run `.venv/bin/python -m pytest -q -p no:xdist tests/unit` with no failures.
- [x] 3.2 Add a CHANGELOG entry stating crew images now pin shared agent assets by commit.
