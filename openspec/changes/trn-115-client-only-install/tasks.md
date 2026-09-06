## 1. scripts/install.sh — flag and early-exit branch

- [ ] 1.1 Add `CLIENT_ONLY=false`, `CLIENT_ONLY_URL="http://localhost:64057/mcp"`, and `CLIENT_ONLY_API_KEY=""` as built-in defaults at the top of `scripts/install.sh` (alongside existing built-in defaults)
- [ ] 1.2 Add `--client-only`, `--url`, and `--api-key` cases to the argument-parser loop in `scripts/install.sh` so they set the three variables above
- [ ] 1.3 After the argument parser, add an early-exit block: if `$CLIENT_ONLY` is true, run only the CLI symlink step (copy from the existing symlink code), call `"$GHOSTSHIP_DIR/ghostship" setup --url "$CLIENT_ONLY_URL" ${CLIENT_ONLY_API_KEY:+--api-key "$CLIENT_ONLY_API_KEY"}`, print the PATH warning if needed, and `exit 0` — skip everything else
- [ ] 1.4 Verify that the full install path executes identically when `--client-only` is not set (no regression to existing argument handling)

## 2. Root shim update

- [ ] 2.1 Confirm that the root `install.sh` shim already forwards all arguments with `"$@"` — add or verify that it does so unconditionally (covers `--client-only` without special-casing)

## 3. ghostship CLI entry point

- [ ] 3.1 Confirm that `ghostship install` already forwards all extra args to `scripts/install.sh` via `_exec_script` — no code change expected; add a comment if it aids clarity

## 4. Documentation

- [ ] 4.1 Add a "Client-only install" section to `README.md` with a brief description, the one-liner example (`./install.sh --client-only --url https://academy.example.com/mcp`), and a note about `--api-key`
- [ ] 4.2 Add a "Client-only install" section to `docs/configuration.md` documenting `--url` (default `http://localhost:64057/mcp`) and `--api-key` (optional)

## 5. Testing and validation

- [ ] 5.1 Run `openspec validate --change trn-115-client-only-install` and confirm no validation errors
- [ ] 5.2 Manually test `./install.sh --client-only` on the local machine (or a CI runner without Podman) — confirm: no Podman check fires, CLI symlink is created, `ghostship setup` runs and wires any detected agents, script exits 0
- [ ] 5.3 Manually test `./install.sh --client-only --url http://localhost:64057/mcp --api-key testkey` — confirm `ghostship setup` receives both flags and registers the MCP entry with an `Authorization: Bearer` header
- [ ] 5.4 Confirm that a plain `./install.sh` (no flags) still runs the full install path without regression
