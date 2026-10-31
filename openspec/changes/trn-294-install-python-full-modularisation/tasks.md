# Tasks

## 1. Scaffolding

- [ ] 1.1 Create `bin/lib/install.py`, `bin/lib/compose.py`, `bin/lib/caddy.py`, `bin/lib/podman.py`, `bin/lib/wizard.py` as empty modules with docstrings and public function stubs matching the interfaces in `design.md`; verify `python3 -c "import bin.lib.compose"` (or equivalent import from GHOSTSHIP_DIR) succeeds without error
- [ ] 1.2 Define `InstallConfig` dataclass (or `TypedDict`) in `bin/lib/install.py` with all fields used across modules; verify `python3 -c "from bin.lib.install import InstallConfig"` succeeds

## 2. compose.py

- [ ] 2.1 Implement `generate_compose(cfg: InstallConfig) -> str` in `bin/lib/compose.py` using dict construction + PyYAML serialisation to replace the bash heredoc (install.sh lines ~1065–1230); verify output matches a known-good `compose.yml` captured from the current install by running a diff
- [ ] 2.2 Add `tests/unit/test_compose.py` covering: correct service names, env var injection, conditional `GA_ORDERS_DIR` volume, conditional `ga-api-key` secret, dashboard port range calculation; verify `pytest tests/unit/test_compose.py` passes

## 3. caddy.py

- [ ] 3.1 Implement `generate_caddy_config(cfg: InstallConfig) -> str` in `bin/lib/caddy.py` using JSON dict construction to replace the bash heredoc (install.sh lines ~1231–1431); verify output matches a known-good `initial-config.json` captured from the current install by running a diff
- [ ] 3.2 Add `tests/unit/test_caddy_install.py` covering: bearer-gated routes, health route without auth, dashboard port range, TLS mode variants (off / acme); verify `pytest tests/unit/test_caddy_install.py` passes

## 4. podman.py

- [ ] 4.1 Implement `check_prerequisites()` in `bin/lib/podman.py` replacing the prerequisite checks (install.sh lines ~547–574): python3 check is now implicit (we're running), podman and podman-compose checks raise `SystemExit` with the same error messages as the bash version; verify `python3 -c "from bin.lib.podman import check_prerequisites; check_prerequisites()"` succeeds on a correctly provisioned host
- [ ] 4.2 Implement `ensure_machine(cfg)` and `resolve_socket(cfg) -> str` in `bin/lib/podman.py` covering macOS (Podman machine create/start, QEMU socket path) and Linux (direct socket path) branches (install.sh lines ~575–791); verify on macOS that `resolve_socket` returns the same path as the bash version; verify on Linux with a mocked `sys.platform`
- [ ] 4.3 Add `tests/unit/test_podman_setup.py` covering: Linux path (mocked `sys.platform == "linux"`), macOS path (mocked subprocess), missing podman raises `SystemExit`; verify `pytest tests/unit/test_podman_setup.py` passes

## 5. wizard.py

- [ ] 5.1 Define `Prompter` protocol (two implementations: `TerminalPrompter` wrapping `input()`, `ScriptedPrompter` consuming a list of answers) and `WizardResult` dataclass in `bin/lib/wizard.py`; verify `python3 -c "from bin.lib.wizard import ScriptedPrompter, WizardResult"` succeeds
- [ ] 5.2 Implement `run_wizard(prompter) -> WizardResult` in `bin/lib/wizard.py` as a direct port of `_interactive_setup()` (install.sh lines ~62–166): backend selection, per-backend config prompts, `config/ghostship.yaml` write; verify `ScriptedPrompter(["kiro", "", "", ""])` produces a `WizardResult` with `agent="kiro"` and writes a valid YAML file to a temp path
- [ ] 5.3 Add `tests/unit/test_wizard.py` covering: kiro-only flow, codex with custom base URL, overwrite-existing-config declined, overwrite accepted; verify `pytest tests/unit/test_wizard.py` passes

## 6. install.py orchestrator

- [ ] 6.1 Implement `main(argv)` in `bin/lib/install.py`: arg parsing (all flags from current install.sh), config resolution via `yaml_config.py`, construction of `InstallConfig`, delegation to `podman.py`, `compose.py`, `caddy.py`, image builds (subprocess), `podman-compose up`, health check loop, wizard + harness registration; verify `python3 bin/lib/install.py --help` prints usage without error
- [ ] 6.2 Replace the body of `bin/install.sh` with the ~50-line glue entry point (`set -e`, PATH bootstrap, python3 availability check, `exec python3 "$GHOSTSHIP_DIR/bin/lib/install.py" "$@"`); verify `./install.sh --help` prints the same usage as before
- [ ] 6.3 Add integration test (or extend `tests/integration/test_install_config.sh`) that runs `python3 bin/lib/install.py` against a known config and asserts the generated `compose.yml` and `initial-config.json` are identical to the bash-generated versions; verify test passes

## 7. Clean-up and final verification

- [ ] 7.1 Remove the bash heredoc sections and all dead code from `bin/install.sh` (verify file is ≤60 lines); verify `wc -l bin/install.sh` reports ≤60
- [ ] 7.2 Run the full unit test suite and verify no regressions: `pytest tests/unit/` passes
- [ ] 7.3 Run a full end-to-end install on corsair (macOS) with a clean config and verify all services come up, `ghostship status` reports healthy, and a crew can be launched
- [ ] 7.4 Update `docs/troubleshooting.md` entries that reference bash functions (`_inject_auth`, etc.) that were in install.sh, if any; verify no stale bash-function references remain in docs

## Workflow follow-up

- Archive the change after the release branch is cut and starport is verified.
