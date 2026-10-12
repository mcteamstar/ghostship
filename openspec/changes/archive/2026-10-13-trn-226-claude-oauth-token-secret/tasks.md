# Tasks

## 1. Remove the broken setup-token route

- [x] 1.1 Delete `_handle_claude_setup_token_post` and both `("POST", "/login/claude/setup-token")` route entries in `transport/server.py`, plus the `_initiate_claude_setup_token` imports. Verify with `grep -rn "setup_token\|setup-token" transport/` returning no route or handler hits.
- [x] 1.2 Delete `_initiate_claude_setup_token` from `transport/lifecycle.py`. Verify that `python -c "import transport.server"` succeeds.
- [x] 1.3 Replace `tests/unit/test_trn226_claude_setup_token.py` with a test asserting `POST /login/claude/setup-token` returns 404 and starts no login container. Verify that test passes and the rest of `tests/unit` stays green.

## 2. Config and secret delivery

- [x] 2.1 Add `CLAUDE_CODE_OAUTH_TOKEN=""` to the install.sh defaults block next to `GA_CREW_ANTHROPIC_API_KEY`, plus an idempotent `ga-claude-code-oauth-token` Podman secret block (rm, then create only when set), mirroring `install.sh:717-725`. Verify by running install with the var set and checking that `podman secret inspect ga-claude-code-oauth-token` succeeds, then running without it (and with `CLAUDE_CODE_OAUTH_TOKEN` exported in the shell) and checking that the secret is gone.
- [x] 2.2 Wire the secret into `compose.yml` generation (the service `secrets:` list and the top-level `external: true` block), conditional on the var, mirroring `install.sh:911` and `:939`. Verify that the generated compose lists the secret only when set and never puts the token in `environment:`.
- [x] 2.3 Add `claude_code_oauth_token` to `Config` and `from_env()` in `transport/config.py`, and add `CLAUDE_CODE_OAUTH_TOKEN` to `_BACKEND_SETTINGS["claude"]`. Verify with a unit test that an inert warning names the var when claude is disabled and does not print the value.
- [x] 2.4 In `transport/server.py`, read `/run/secrets/ga-claude-code-oauth-token` into `_CLAUDE_CODE_OAUTH_TOKEN` (env-var fallback for dev/test) and call `_security.register_secret` on it, mirroring the Anthropic key block. Verify with a unit test that the secret file value wins over the env var and is redacted from a logged string.
- [x] 2.6 Resolve `KIRO_API_KEY`, `GA_CREW_ANTHROPIC_API_KEY`, `GA_CREW_OPENAI_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN` through `security.get_secret` in both `server.py` and `lifecycle.py` (drop `_read_podman_secret`), and make `_warn_inert_backend_settings` check the resolved values. Verify with a source test that both modules resolve each credential from its secret, and that the inert warning fires from the resolved value.
- [x] 2.5 Add a secret-delivery test, alongside the existing anthropic-key compose tests, covering the three install scenarios in `specs/secret-delivery-hardening/spec.md`. Verify that it passes.

## 3. Crew injection, precedence and launch gate

- [x] 3.1 In the `container_env` build (`server.py:2785`), set `CLAUDE_CODE_OAUTH_TOKEN` only when the backend is claude, `_GA_CREW_ANTHROPIC_API_KEY` is empty and the token is set. Verify with unit tests for the "Token injected at launch", "API key outranks the token" and "Token not injected into non-Claude crews" scenarios.
- [x] 3.2 Resolve the token in lifecycle (task 2.6), and change the guard at `lifecycle.py:2146` to `not GA_CREW_ANTHROPIC_API_KEY and not CLAUDE_CODE_OAUTH_TOKEN and _claude_auth_exists()`. Verify with a unit test that `_inject_claude_auth` is not called when the token is set and `ga-claude-auth` exists, and still is called when neither key is set.
- [x] 3.3 Extend the launch gate at `server.py:2628` to accept the token. Verify with unit tests that launch with only the token creates the crew without a login container, and that launch with no credential still returns `not_authenticated` with a login URL.

## 4. Documentation

- [x] 4.1 Rewrite the "Claude headless auth (recommended)" section of `docs/auth.md`: run `claude setup-token` locally, set `CLAUDE_CODE_OAUTH_TOKEN`, reinstall, relaunch crews, the precedence order, and rotation on expiry. Remove the `POST /login/claude/setup-token` API docs and scope the "may expire" note to OAuth only. Verify that `grep -n "login/claude/setup-token" docs/` returns nothing.
- [x] 4.2 Add a commented `CLAUDE_CODE_OAUTH_TOKEN` entry to `config/ghostship.conf.example` next to `GA_CREW_ANTHROPIC_API_KEY`, noting precedence. Verify by sourcing the example in a subshell without errors.
- [x] 4.3 Add a CHANGELOG entry tagged TRN-226: the new token setting, the **BREAKING** removal of `POST /login/claude/setup-token`, and migration steps. Verify that the entry names both the var and the removed route.

## 6. Rename the model backend settings

- [x] 6.1 Rename `GA_CREW_ANTHROPIC_API_KEY`/`_BASE_URL` and `GA_CREW_OPENAI_API_KEY`/`_BASE_URL` to `ANTHROPIC_*`/`OPENAI_*` across `install.sh`, `transport/`, tests, `docs/` and `config/ghostship.conf.example`, keeping the `ga-crew-*` secret names. Verify with `git grep` showing no old names outside openspec, the historical CHANGELOG and the 0.6.0 release notes.
- [x] 6.2 Add install.sh defaults for both old and new names, plus a mapping block that warns on old names and lets the new name win. Verify with unit tests that run the real defaults and mapping blocks under bash (mapping, precedence, no value in warnings, silence with new names, shell values ignored).
- [x] 6.3 Note the old names in `docs/configuration.md`, `docs/auth.md`, `config/ghostship.conf.example` and the CHANGELOG Deprecations section. Verify that each renamed row in `docs/configuration.md` names its old setting.
- [x] 6.4 Run the full unit suite and verify that it passes.
- [x] 6.5 Reinstall with the real config and confirm a Claude crew still works, then run the negative checks: a bad token makes model calls fail, and no credential makes launch return `not_authenticated`. Restore the real config and confirm a crew works again.

## 5. Integration check

- [x] 5.1 Run the full unit suite and verify that it passes.
- [x] 5.2 On a local install with a real token in `ghostship.conf`, run `ghostship install`, launch a headless crew, dispatch a trivial ghost task and confirm it completes on the Claude backend with no login prompt. Then nuke the crew.

## Workflow follow-up

- Run an independent review (banshee) before archive.
- Sync specs and archive the change after review.
