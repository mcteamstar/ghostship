# Tasks

## 1. Thread the backend through crew config patching

- [x] 1.1 Give `lifecycle._patch_crew_config` and `lifecycle._patch_models` a required `backend` keyword and use it in place of `GA_CREW_ACP_BACKEND` for `acp_backend`, `default_model` and the model override; verify with unit tests that a `kiro` crew under a `claude` default gets no `acp_backend` and the kiro model settings, and that a `claude` crew gets `acp_backend: "claude"`; update the existing `_patch_crew_config` mocks in `tests/unit/test_lifecycle.py` to assert the `backend` keyword
- [x] 1.2 Update both restart paths in `transport/launcher.py` (concurrent restart and reconcile restart) to pass the crew's recorded `acp_backend` (missing → `kiro`); verify with a unit test that restarting a kiro crew while the default is `claude` re-patches it as kiro

## 2. Per-crew backend in launch

- [x] 2.1 Add the optional `backend` argument to `tools.launch`, normalise it, default to `GA_CREW_ACP_BACKEND`, and reject values outside the enabled set with the `backend_not_enabled` error shape from design.md; verify with unit tests for omitted, explicit, disabled (`codex` when not enabled), unknown (`gemini`) and always-enabled `kiro`, and that rejected calls create no container or registry entry. Replace the "defensive" default-backend enabled check and its comment (`tools.py` ~line 578) with this validation
- [x] 2.2 Key the credential lookup, not-authenticated login flows and container env injection in `tools.launch` on the resolved backend; verify with unit tests that a `kiro` launch under a `claude` default starts the kiro device flow when kiro has no credential, and receives no claude env vars when both are stored
- [x] 2.3 Pass `backend` into `launcher.finish_setup` and use it for post-start auth injection, `_patch_crew_config`/`_patch_models` and `Crew(acp_backend=...)`; verify with a unit test that the registry entry and `crews()` report the requested backend
- [x] 2.4 Document `backend` in the `launch` MCP tool docstring (values, default, enabled-set rule); verify the tool schema lists the optional `backend` parameter

## 3. Docs and skill guidance

- [x] 3.1 Update `docs/configuration.md` / `docs/architecture.md` where they say the default backend applies to every crew, and add a `launch(..., backend=...)` example; verify by reading the rendered sections
- [x] 3.2 Update `.claude-plugin/skills/ghostship-command/SKILL.md` launch guidance to mention `backend`; verify the example call matches the tool signature
- [x] 3.3 Add an `## Unreleased` entry to `CHANGELOG.md` covering the `backend` argument and the restart fix (existing crews now keep their recorded backend across restarts); verify the entry names both

## 4. Integration check

- [x] 4.1 Run `tests/run.sh --unit`; verify it passes
- [x] 4.2 On a reinstalled transport with claude as default and both kiro and claude logged in, launch one crew with `backend="kiro"` and one with no backend, dispatch a trivial task to each, and verify `crews()` shows `kiro` and `claude` respectively and both tasks complete
