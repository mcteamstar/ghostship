# Tasks: secret-handling-hardening

## 1. install.sh — add Podman secrets for crew model keys and KIRO_API_KEY

- [ ] 1.1 Add `GA_CREW_OPENAI_API_KEY` variable declaration to the defaults block (alongside `GA_CREW_ANTHROPIC_API_KEY` which already exists) and wire it to `--openai-api-key` flag parsing (mirrors the existing `--anthropic-api-key` flag, if present; add if missing)
- [ ] 1.2 Add a "Podman secret for ga-crew-anthropic-api-key" block after the existing `ga-api-key` block: `podman secret rm ga-crew-anthropic-api-key 2>/dev/null || true`, then `printf '%s' "$GA_CREW_ANTHROPIC_API_KEY" | podman secret create ga-crew-anthropic-api-key -` when `GA_CREW_ANTHROPIC_API_KEY` is non-empty
- [ ] 1.3 Add a "Podman secret for ga-crew-openai-api-key" block in the same location: same pattern as 1.2 guarded by `GA_CREW_OPENAI_API_KEY`
- [ ] 1.4 Add a "Podman secret for ga-kiro-api-key" block: same pattern guarded by `KIRO_API_KEY`

## 2. install.sh — update compose.yml template

- [ ] 2.1 Remove `GA_CREW_ANTHROPIC_API_KEY` and `GA_CREW_OPENAI_API_KEY` from the `environment:` block of the `ga-transport` service in the compose.yml heredoc
- [ ] 2.2 Remove `KIRO_API_KEY` from the `environment:` block of `ga-transport` (if currently present; add removal guard comment if it was never added)
- [ ] 2.3 Add conditional `- ga-crew-anthropic-api-key` to the `ga-transport` `secrets:` list (guarded by `GA_CREW_ANTHROPIC_API_KEY` non-empty, same `$(if [...]; then printf ...)` pattern as `ga-api-key`)
- [ ] 2.4 Add conditional `- ga-crew-openai-api-key` to the `ga-transport` `secrets:` list (guarded by `GA_CREW_OPENAI_API_KEY`)
- [ ] 2.5 Add conditional `- ga-kiro-api-key` to the `ga-transport` `secrets:` list (guarded by `KIRO_API_KEY`)
- [ ] 2.6 Add conditional `ga-crew-anthropic-api-key:`, `ga-crew-openai-api-key:`, and `ga-kiro-api-key:` entries (each `external: true`) to the top-level `secrets:` block of the compose heredoc

## 3. transport/server.py — read crew secrets from /run/secrets/

- [ ] 3.1 Add a `_read_podman_secret(name)` helper (or reuse/extend the existing one used for `ga-api-key`) that opens `/run/secrets/<name>`, strips whitespace, and returns `""` on `FileNotFoundError`
- [ ] 3.2 After `cfg = Config.from_env()`, read `/run/secrets/ga-crew-anthropic-api-key` and overwrite `_GA_CREW_ANTHROPIC_API_KEY` (the module-level variable) with the file value when non-empty; leave it unchanged (env-var value, now always `""`) otherwise
- [ ] 3.3 Same as 3.2 for `_GA_CREW_OPENAI_API_KEY` ← `/run/secrets/ga-crew-openai-api-key`
- [ ] 3.4 Same as 3.2 for `KIRO_API_KEY` ← `/run/secrets/ga-kiro-api-key`
- [ ] 3.5 Ensure `_security.register_secret(...)` is called on all three values after the secret-file read (it is currently called on the env-var values; move or duplicate the call to cover the file-sourced path)

## 4. Verification

- [ ] 4.1 Run `install.sh` in a test environment with `GA_CREW_ANTHROPIC_API_KEY`, `GA_CREW_OPENAI_API_KEY`, and `KIRO_API_KEY` set; confirm `podman secret ls` shows `ga-crew-anthropic-api-key`, `ga-crew-openai-api-key`, and `ga-kiro-api-key`
- [ ] 4.2 Confirm the generated `compose.yml` does not contain any of the three key values in its `environment:` block
- [ ] 4.3 Start `ga-transport` and verify `/run/secrets/ga-crew-anthropic-api-key` (and siblings) are mounted and readable inside the container
- [ ] 4.4 Run `install.sh` a second time (idempotency check); confirm no error and secrets are recreated with the new values
- [ ] 4.5 Run `install.sh` with keys absent; confirm no dangling secret references in `compose.yml` and transport starts without error (falls back to device-code for kiro, OAuth for model backends)
- [ ] 4.6 Run existing integration tests (`tests/integration/test_install_config.sh`, `test_dedicated_transport.sh`) and confirm no regressions
