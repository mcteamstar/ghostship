# Tasks

## 1. Phase 1 — compose.py

- [x] 1.1 Create `bin/lib/compose.py` with a `ComposeConfig` dataclass covering
  all compose.yml fields (services, networks, secrets, volumes, env vars) and a
  `generate_compose(config: ComposeConfig) -> str` function that returns a
  PyYAML-serialised YAML string; verify the module is importable with
  `python3 -c "from bin.lib.compose import generate_compose"` from the repo root
  (with `PYTHONPATH=bin/lib/vendor`).

- [x] 1.2 Implement the conditional compose sections in `compose.py`:
  `GA_API_KEY` secret mount, `GA_ORDERS_DIR` bind mount, `GA_TLS_CERTFILE`/
  `GA_TLS_KEYFILE` bind mount, per-dashboard-port range; verify each condition
  by asserting the rendered YAML includes or omits the relevant stanza for
  controlled inputs.

- [x] 1.3 Add `tests/unit/test_compose.py` covering at least: (a) minimal config
  produces all three services, (b) with `GA_API_KEY` set the secret mount appears,
  (c) without `GA_API_KEY` no `ga-api-key` secret is declared, (d) missing required
  field raises `ValueError`; verify `pytest tests/unit/test_compose.py` passes.

- [x] 1.4 Replace the compose.yml heredoc in `bin/install.sh` (lines ~1065–1230)
  with a call to `compose.py` via `python3 bin/lib/compose.py --output "$DATA_DIR/compose.yml"`;
  add a `--output` CLI entry point to `compose.py`; verify `bash -n bin/install.sh`
  passes and `grep -c 'cat >' bin/install.sh` returns 0.

## 2. Phase 2 — caddy.py

- [x] 2.1 Create `bin/lib/caddy.py` with a `CaddyConfig` dataclass and a
  `generate_caddy_config(config: CaddyConfig) -> dict` function that returns
  the `initial-config.json` structure as a Python dict; verify importable.

- [x] 2.2 Implement all four TLS mode stanzas (`off`, `internal`, `tailscale`,
  `acme`) and both route variants (API-key-gated vs passthrough) in `caddy.py`;
  verify each variant by asserting dict structure for controlled inputs.

- [x] 2.3 Implement the Radar session-gated route and the `ga-transport-misc`
  catch-all route in `caddy.py`; verify that the generated JSON matches the
  structure currently in the heredoc by comparing key paths.

- [x] 2.4 Add `tests/unit/test_caddy.py` covering: (a) TLS mode `off` sets
  `automatic_https.disable: true`, (b) with API key gated routes include a
  `401` handler, (c) without API key no `401` handler present, (d) `acme` mode
  includes the ACME domain in the TLS policy; verify `pytest tests/unit/test_caddy.py` passes.

- [x] 2.5 Replace the Caddy JSON heredoc in `bin/install.sh` with a call to
  `python3 bin/lib/caddy.py --output "$DATA_DIR/caddy/initial-config.json"`;
  verify `bash -n bin/install.sh` passes and no JSON heredoc remains in the file.

## 3. Phase 3 — Python ports of agent_backends.sh / portal_host.sh

- [x] 3.1 Create `bin/lib/agent_backends.py` implementing `normalise(raw: str) -> str`,
  `available(toolchains_dir: str) -> str`, `validate(list_str: str, toolchains_dir: str)`,
  `check_default(default: str, list_str: str, toolchains_dir: str)`, and
  `reject_retired(env: dict)` — matching the exact bash semantics; verify the
  existing `tests/unit/test_agent_backends_parity.py` passes after adding a Python
  call path (update the test to also import from `agent_backends.py`).

- [x] 3.2 Create `bin/lib/portal_host.py` implementing `is_loopback(host: str) -> bool`,
  `is_wildcard(host: str) -> bool`, `addr(host: str) -> str`, `public_base(host: str, port: str) -> str`,
  `probe_base(host: str, port: str, scheme: str) -> str`, `resolve_api_key(...)`,
  and `check_exposure(host: str, port: str, ga_api_key: str, ga_api_key_disabled: str)`;
  verify each function against equivalent `portal_host.sh` calls in a new
  `tests/unit/test_portal_host.py`.

- [x] 3.3 Add `tests/unit/test_portal_host.py` covering: (a) empty host is
  loopback, (b) `127.0.0.1` is loopback, (c) `0.0.0.0` is wildcard but not
  loopback, (d) `example.com` is neither; `probe_base` returns bracketed IPv6
  literals; verify `pytest tests/unit/test_portal_host.py` passes.

- [x] 3.4 Reduce `bin/lib/agent_backends.sh` to a one-line delegator
  (`exec python3 "$(dirname "$0")/agent_backends.py" "$@"`) with a deprecation
  comment; do the same for `bin/lib/portal_host.sh`; verify `bash -n` passes for
  both and verify the existing `tests/unit/test_install.py` static assertions
  still pass.

- [x] 3.5 Update `bin/install.sh` to call `agent_backends.py` and `portal_host.py`
  via `python3` rather than sourcing the `.sh` files; verify `bash -n bin/install.sh`
  passes and `pytest tests/unit/test_install.py` passes.

## 4. Phase 4 — podman_setup.py

- [x] 4.1 Create `bin/lib/podman_setup.py` implementing `setup_podman_linux(config)`,
  `setup_podman_macos(config)`, and `resolve_socket_path(config) -> str`; all
  Podman calls use `subprocess.run([...], check=True)` with no `eval`; verify
  importable and add stubs/mocks for the subprocess calls in
  `tests/unit/test_podman_setup.py`.

- [x] 4.2 Implement the dedicated-instance path for Linux in `podman_setup.py`:
  write the systemd service unit via Python file I/O, call
  `systemctl --user daemon-reload` and `enable --now` via subprocess; verify the
  unit content is correct by asserting the rendered string in
  `tests/unit/test_podman_setup.py`.

- [x] 4.3 Implement the dedicated-machine path for macOS in `podman_setup.py`:
  `podman machine list`, `init`, `start`, `ssh` calls via subprocess; bounded
  socket-ready retry loop; verify tests mock these calls and assert bounded retry
  behaviour with a configurable attempt count.

- [x] 4.4 Implement `resolve_socket_path` for the default Linux instance:
  derive from `XDG_RUNTIME_DIR` and `id -u` via subprocess with captured output
  (no eval); verify tests assert the correct path for controlled env inputs.

- [x] 4.5 Add `tests/unit/test_podman_setup.py` covering: (a) missing socket
  after max retries raises `RuntimeError` with a diagnostic message, (b) Linux
  socket path computed correctly from `XDG_RUNTIME_DIR`, (c) dedicated-instance
  systemd unit content contains correct `--root` and `--runroot` paths; verify
  `pytest tests/unit/test_podman_setup.py` passes.

- [x] 4.6 Replace the Podman provisioning blocks in `bin/install.sh` (machine
  init/start, socket resolution, systemd unit, containers.conf writing) with a call
  to `python3 bin/lib/podman_setup.py`; verify `bash -n bin/install.sh` passes
  and `pytest tests/unit/test_podman_setup.py` passes.

## 5. Phase 5 — wizard.py

- [x] 5.1 Create `bin/lib/wizard.py` with `interactive_setup(env: dict, input_fn=input, print_fn=print) -> dict`
  implementing the backend selection loop, non-secret config prompts, and
  `config/ghostship.yaml` generation; dependency-injected I/O callables allow
  tests to supply canned answers without patching builtins; verify importable.

- [x] 5.2 Implement `post_install_auth(env: dict, ghostship_bin: str, input_fn=input)` in
  `wizard.py` for the post-transport auth-offer loop (iterate enabled backends,
  call `ghostship auth login <backend>` for unconfigured ones); verify tests
  mock the subprocess and assert the correct backends are offered.

- [x] 5.3 Add `tests/unit/test_wizard.py` covering: (a) unknown backend re-prompts
  rather than exiting, (b) existing config with `_overwrite=n` returns without
  writing, (c) kiro backend prompts for identity-provider URL, (d) post-install auth
  skips already-configured backends; verify `pytest tests/unit/test_wizard.py` passes.

- [x] 5.4 Replace `_interactive_setup()` and the post-install auth block in
  `bin/install.sh` with `python3 bin/lib/wizard.py --mode setup` and
  `python3 bin/lib/wizard.py --mode post-auth`; verify `bash -n bin/install.sh`
  passes and `pytest tests/unit/test_wizard.py` passes.

## 6. Phase 6 — install_main.py / exec-to-Python / eval elimination

- [x] 6.1 Create `bin/lib/install_main.py` as the Python entry point: parses all
  install.sh flags (using `argparse`), calls `yaml_config.resolve_config(...)` directly
  (import, no subprocess eval), and orchestrates calls to `podman_setup`,
  `compose`, `caddy`, and optionally `wizard`; verify importable and that the
  argparse help matches all current `install.sh` flags.

- [x] 6.2 Shrink `bin/install.sh` to a ≤100-line prereq-check and
  `exec python3 "$(dirname "$0")/lib/install_main.py" "$@"` entry point;
  verify `wc -l bin/install.sh` ≤ 100 and `bash -n bin/install.sh` passes.

- [x] 6.3 Remove the `eval "$_RESOLVED"` line from `bin/install.sh`; verify
  `grep -c 'eval "\$_RESOLVED"' bin/install.sh` returns 0.

- [x] 6.4 Update `bin/start.sh` to import yaml_config directly (via a new thin
  `bin/lib/start_ops.py`) and remove its `eval "$_RESOLVED"` pattern; verify
  `grep -c 'eval "\$_RESOLVED"' bin/start.sh` returns 0 and `bash -n bin/start.sh`
  passes.

- [x] 6.5 Update `bin/uninstall.sh` analogously (via `bin/lib/uninstall_ops.py`);
  verify `grep -c 'eval "\$_RESOLVED"' bin/uninstall.sh` returns 0 and
  `bash -n bin/uninstall.sh` passes.

- [x] 6.6 Assert the eval elimination spec requirement: add a test to
  `tests/unit/test_install.py` that greps `install.sh`, `start.sh`, and
  `uninstall.sh` for any `eval "$(..."` or `eval "$(...)"` pattern and asserts
  none are present; verify `pytest tests/unit/test_install.py` passes.

## 7. Integration verification

- [ ] 7.1 Run the full unit test suite (`pytest tests/unit/`) and confirm zero
  failures; this exercises all new modules and the updated parity tests.

- [ ] 7.2 Run `bash -n bin/install.sh bin/start.sh bin/uninstall.sh` to assert
  all three scripts are syntactically valid bash; confirm exit code 0.

- [ ] 7.3 Run `openspec validate --change trn-294-install-python-full-modularisation`
  and confirm the change passes validation.

- [ ] 7.4 Assert `bin/install.sh` line count: run
  `grep -vc '^\s*$\|^\s*#' bin/install.sh` and confirm the result is ≤100.

- [ ] 7.5 Assert no heredoc YAML/JSON in install.sh: run
  `grep -c 'cat >' bin/install.sh` and confirm the result is 0.

- [ ] 7.6 Assert no eval of subprocess output: run
  `grep -Pc 'eval "\$\(\.+\)"' bin/install.sh bin/start.sh bin/uninstall.sh`
  and confirm the result is 0.

## Workflow follow-up

- Dispatch Ghost to implement the tasks.
- After implementation, run the full test suite once more before archiving.
- Archive the change after review requirements are satisfied.
