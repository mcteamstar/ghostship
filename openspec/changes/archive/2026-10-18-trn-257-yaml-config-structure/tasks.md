# Tasks

## 1. yaml_config.py — key map, deprecated-path rewrite, list handling

- [x] 1.1 Update `_KEY_MAP` with all new YAML paths (16 path changes + 6 new per-backend model paths). Update `DEFAULTS` for renamed keys. Add new per-backend model env var defaults (empty strings). Verify: `python3 scripts/lib/yaml_config.py resolve --repo /dev/null --xdg /dev/null` emits all expected env vars with defaults including new `KC_MODEL_*` vars.
- [x] 1.2 Add `_DEPRECATED_YAML_PATHS` table mapping old tuple-paths to new ones (16 entries + `model.override` → discard). Implement `_rewrite_deprecated_yaml_paths(tree)` — rewrites old paths to new, warns per remapping, discards `model.override` with a targeted warning. Call in `resolve_config` before `flatten_to_env`. Verify: YAML file using `crew.git_author_name` warns and resolves `GA_GIT_AUTHOR_NAME`; `model.override` warns and is ignored.
- [x] 1.3 Handle `backends.default` list type in `flatten_to_env`: list → join with `,`; string → use as-is with deprecation warning. Verify: `backends.default: [kiro, claude]` resolves `GA_CREW_AGENT=kiro,claude`; string form warns.

## 2. transport/config.py — per-backend model fields and precedence

- [x] 2.1 Add six new `Config` fields: `kc_model_kiro_override`, `kc_model_kiro_default`, `kc_model_claude_override`, `kc_model_claude_default`, `kc_model_codex_override`, `kc_model_codex_default` (all `str = ""`). Add corresponding `from_env()` reads for `KC_MODEL_KIRO_OVERRIDE` etc. Verify: `Config.from_env()` reads the new vars; unset vars default to `""`.
- [x] 2.2 Update model precedence resolution in the transport (wherever model is selected for a crew spawn — `lifecycle.py` or equivalent): implement the full chain `dispatch > backend_override > per-agent > backend_default > global_default > built-in`. Verify: unit tests cover each precedence level winning correctly.

## 3. config/ghostship.yaml.example

- [x] 3.1 Rewrite `config/ghostship.yaml.example` using the full new structure: `machine.images`, `crew.git.author`, `network.tls`, `backends.kiro.identity_center`, `backends.<b>.model.override/default`, `portal.dashboard.port_range`, `machine.resources`. Include commented `- claude` and `- codex` under `backends.default`. Verify: `python3 -c "import yaml; yaml.safe_load(open('config/ghostship.yaml.example'))"` parses cleanly and spot-checks pass.

## 4. Tests

- [x] 4.1 Update `tests/unit/test_yaml_config.py` — fix all path tuple references to new paths. Add tests for: deprecated-path warning + value resolution for a sample of old paths; `model.override` discard warning; `backends.default` as list; `backends.default` as string (deprecated); per-backend model env vars emitted correctly. Verify: `pytest tests/unit/test_yaml_config.py` passes.
- [x] 4.2 Update `tests/unit/test_config.py` sync invariant — new Config fields covered in `ghostship.yaml.example`. Verify: `pytest tests/unit/test_config.py -k yaml_example` passes.
- [x] 4.3 Add or update unit tests for transport model precedence in the appropriate test file. Verify: all six precedence levels covered; `pytest tests/unit/` passes.

## 5. Docs

- [x] 5.1 Update `docs/configuration.md` — replace all old YAML key path references with new paths; rewrite the Model section to document the full precedence chain with the chain diagram, an explanation of each level, and examples (when to use backend override vs backend default vs global default); add a migration note for `model.override` removal. Verify: no old paths remain; the precedence chain is clearly documented.

## 6. Integration check

- [x] 6.1 Run full unit suite and confirm no new failures beyond pre-existing. Verify: `pytest tests/unit/` exits 0 with no new failures.

## Workflow follow-up

- Commit to `release/0.8.0`, push to origin.
- Assimilate and archive after review.
