# Tasks

## 1. `ghostship upgrade --skills`

- [x] 1.1 Rewrite `cmd_upgrade` in `ghostship` to accept `--skills`: strip the flag from args, run `scripts/install.sh` via `subprocess.run` (inheriting stdio), and on exit 0 call `cmd_setup([])` in-process; forward the combined exit code. Verify: `ghostship upgrade --help` documents `--skills`; running `ghostship upgrade --skills` with a mock install succeeds and calls setup.
- [x] 1.2 Add unit tests to `tests/unit/test_ghostship_cli.py` for `cmd_upgrade --skills` covering: install success → setup called; install failure → setup not called; no `--skills` → unchanged behaviour (setup not called). Verify: `pytest tests/unit/test_ghostship_cli.py -k upgrade` passes.

## 2. `ghostship skills` subcommand

- [x] 2.1 Add a `cmd_skills` function to `ghostship` that prints its own `--help` text (mentions "equivalent to `ghostship setup`") and delegates to `cmd_setup`. Register `"skills": cmd_skills` in the dispatch table and add it to the `--help` summary. Verify: `ghostship skills --help` prints usage; `ghostship skills` with no agent clients present exits 0 with "no supported agent found".
- [x] 2.2 Add unit tests for `cmd_skills` in `tests/unit/test_ghostship_cli.py`: `--help` exits 0; no-agent case exits 0; `--agent kiro` flag forwarded correctly. Verify: `pytest tests/unit/test_ghostship_cli.py -k skills` passes.

## 3. Wizard unconditional setup

- [x] 3.1 In `scripts/install.sh`, replace the `_prompt`-gated `ghostship setup` block (lines ~1509–1516) with an unconditional call: `"${GHOSTSHIP_DIR}/ghostship" setup || true`. Verify: `bash -n scripts/install.sh` passes; running `./install.sh --wizard` in a sandbox completes and calls setup without prompting.
- [x] 3.2 Add or update the integration test `tests/integration/test_install_wizard.sh` (or equivalent) to assert that a wizard run results in `ghostship setup` being called without a confirmation prompt. Verify: the integration test passes.

## 4. Docs and final check

- [x] 4.1 Update `docs/configuration.md` or `README.md` "Upgrade" section to document `ghostship upgrade --skills` and `ghostship skills`. Verify: the documented commands run without error.
- [x] 4.2 Run the full unit suite (`tests/run.sh` or `pytest tests/unit/`) and confirm all tests pass. Verify: exit 0 with no new failures.

## Workflow follow-up

- Commit changes to `release/0.8.0`, push to origin.
- Archive the change after review.
