# Tasks: trn-268-indy-081-hotfixes

## 1. Release version bump

- [x] 1.1 In `VERSION`, change `0.8.0` to `0.8.1`. Verify: `cat VERSION` outputs `0.8.1`.
- [x] 1.2 In `.claude-plugin/plugin.json`, change `"version": "0.8.0"` to `"version": "0.8.1"`. Verify: `grep '"version"' .claude-plugin/plugin.json` shows `0.8.1`.
- [x] 1.3 In `.claude-plugin/.claude-plugin/plugin.json`, same change. Verify: `grep '"version"' .claude-plugin/.claude-plugin/plugin.json` shows `0.8.1`.
- [x] 1.4 Commit with message `release: v0.8.1` covering all three files (design Decision 1). Verify: `git show --stat HEAD` names all three files and the message starts with `release:`.

## 2. Pin AGENTS_REF

- [x] 2.1 Confirm the current tip SHA of `mcteamstar/.agents` by running `git ls-remote https://github.com/mcteamstar/.agents.git HEAD` and recording the 40-character SHA. Use this live value (not the planning-time value in design.md) if it has moved.
- [x] 2.2 In `crews/spec-ops/Containerfile`, change `ARG AGENTS_REF="main"` to `ARG AGENTS_REF="<confirmed-sha>"`. Update the adjacent comment to read: `# AGENTS_REF pins to a specific SHA — bump deliberately for each .agents update; a changed SHA triggers a cache-less rebuild via the org.ghostship.agents_ref label.` (design Decision 2). Verify: `grep 'AGENTS_REF' crews/spec-ops/Containerfile` shows the full 40-character SHA, not `main`.
- [x] 2.3 Run the unit suite to confirm no tests reference or assert `AGENTS_REF="main"`: `pytest tests/unit/ -q`. Verify: exits 0.

## 3. macOS CA cert extraction hint

- [x] 3.1 In `ghostship` (CLI), inside `cmd_status`, locate the block that prints `CA cert: {cert_path}` (the `if mountpoint is not None` branch under `if portal_tls_mode == "internal"`). After the `print(f"  CA cert:   {cert_path}")` line, add: `machine = os.environ.get("GA_MACHINE_NAME", "ghost-academy"); if sys.platform == "darwin": print(f"  (VM path — to extract to host, run:)"); print(f"    podman machine ssh {machine} cat {cert_path} > ~/ghost-academy-root.crt"); print(f"  Then trust: sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ~/ghost-academy-root.crt")` (design Decision 3). Verify: a unit test with `sys.platform` patched to `"darwin"`, `_portal_data_mountpoint` returning a non-None mountpoint, and `GA_PORTAL_TLS_MODE=internal` asserts that captured stdout contains `podman machine ssh` and `security add-trusted-cert`; a companion test with `sys.platform` patched to `"linux"` asserts neither string appears.
- [x] 3.2 In `bin/install.sh`, inside the `if [[ "${GA_PORTAL_TLS_MODE:-off}" == "internal" ]]` block, after the `echo "Root CA cert: ${_CADDY_ROOT_CERT_PATH}"` line, add a macOS-only hint block (design Decision 3): `if [[ "$(uname -s)" == "Darwin" ]] && [[ -n "${_CADDY_DATA_MOUNTPOINT}" ]]; then echo "  (VM path — to extract to host, run:)"; echo "    podman machine ssh ${_MACHINE} cat ${_CADDY_ROOT_CERT_PATH} > ~/ghost-academy-root.crt"; echo "  Then trust it: sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ~/ghost-academy-root.crt"; fi`. `_MACHINE` is already resolved earlier in the script. Verify: `grep -A5 'uname.*Darwin' bin/install.sh` shows the hint lines; `bash -n bin/install.sh` exits 0.
- [x] 3.3 Run the full unit suite: `pytest tests/unit/ -q`. Verify: exits 0.

## 4. Verification

- [x] 4.1 Confirm `grep -r '"version"' .claude-plugin/` shows `0.8.1` in both manifests, and `cat VERSION` shows `0.8.1`.
- [x] 4.2 Confirm `grep 'AGENTS_REF' crews/spec-ops/Containerfile` shows the pinned SHA (no `main`).
- [x] 4.3 Confirm `bash -n bin/install.sh` and `python3 -c "import py_compile; py_compile.compile('ghostship')"` both exit 0.
- [x] 4.4 Run full unit suite: `bash scripts/run.sh --unit`. Verify: exits 0.
