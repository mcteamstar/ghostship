# TRN-218 KAS ACP backend — tasks

## 1. Config allowlist (`transport/config.py`)

- [ ] 1.1 Add `"kas"` to `_ACP_BACKEND_VALUES` frozenset
- [ ] 1.2 Update the hardcoded prose list in `_validate_acp_backend`'s `ConfigError` message to include `'kas'`
- [ ] 1.3 Confirm no change needed to `_BACKEND_SETTINGS` / `_BACKEND_CREDENTIAL_FILES` (KAS has no optional credential) and leave them unchanged

## 2. Config-write branch (`transport/lifecycle.py`)

- [ ] 2.1 Add `elif GA_CREW_ACP_BACKEND == "kas":` branch in `_patch_crew_config` that sets `agent_overrides["acp_backend"] = "kas"`
- [ ] 2.2 Add the explanatory comment noting KAS is 0.9.0-only and reuses the kiro identity
- [ ] 2.3 Verify the `kiro` default case still writes no `acp_backend` key (unchanged)

## 3. Credential model (verification, not new code)

- [ ] 3.1 Confirm `_finish_crew_setup`'s `else` (kiro) branch is reached for `GA_CREW_ACP_BACKEND=kas` — no edit required
- [ ] 3.2 Verify no login-container path (`_initiate_*_login`) is added for KAS
- [ ] 3.3 **Open question:** confirm against the KiroCrew 0.9.0 gateway that KAS authenticates off the injected kiro-cli auth rows / `KIRO_API_KEY` and needs no distinct KAS credential; if it does, escalate — this becomes a login-flow task, not a config task

## 4. Registry (verification)

- [ ] 4.1 Confirm `_finish_crew_setup` records `"acp_backend": GA_CREW_ACP_BACKEND` generically — stores `"kas"` with no code change
- [ ] 4.2 Confirm `crews()` surfaces `acp_backend: "kas"` from the registry entry

## 5. Tests (`tests/unit/`)

- [ ] 5.1 `Config.from_env()` with `GA_CREW_ACP_BACKEND=kas` + `GA_AGENT_BACKENDS=kas` constructs without raising
- [ ] 5.2 `_validate_acp_backend("kas") == "kas"`; an out-of-set value still raises `ConfigError`
- [ ] 5.3 `parse_agent_backends("kas") == ("kas",)`
- [ ] 5.4 `_validate_default_backend` rejects `kas` when not enabled, accepts it when enabled
- [ ] 5.5 `_patch_crew_config` with `kas` yields `agent.acp_backend == "kas"` in the override payload (mirror existing claude/codex tests)
- [ ] 5.6 `_finish_crew_setup` with `kas` calls `_inject_auth` and not `_inject_claude_auth`/`_inject_codex_auth`

## 6. Documentation

- [ ] 6.1 `docs/configuration.md`: list `kas` as a valid `GA_CREW_ACP_BACKEND` / `GA_AGENT_BACKENDS` value
- [ ] 6.2 `docs/auth.md`: document that KAS uses the operator's existing kiro-cli identity (no separate login)

## 7. Dependency gate

- [ ] 7.1 Verify the KiroCrew base image is `0.9.0-insider.4` or later before enabling `kas` in any real crew (KAS runtime does not exist in 0.8.0); cross-reference TRN-219 / the KC 0.9.0 upgrade change
