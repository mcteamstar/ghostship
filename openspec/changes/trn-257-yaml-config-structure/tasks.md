# Tasks

## 1. yaml_config.py — key map and deprecated-path rewrite

- [ ] 1.1 Update `_KEY_MAP` with all 13 new YAML paths. Update `DEFAULTS` keys where path segments changed (no env var changes). Verify: `python3 scripts/lib/yaml_config.py resolve --repo /dev/null --xdg /dev/null` emits all expected env vars with defaults.
- [ ] 1.2 Add `_DEPRECATED_YAML_PATHS` table mapping old tuple-paths to new ones. Implement `_rewrite_deprecated_yaml_paths(tree)` — rewrites old paths to new in the merged tree, warns per mapping found. Call it in `resolve_config` before `flatten_to_env`. Verify: a YAML file using `crew.git_author_name` emits a warning and resolves `GA_GIT_AUTHOR_NAME` correctly.
- [ ] 1.3 Handle `backends.default` list type in `flatten_to_env`: if the resolved value for `("backends", "default")` is a list, join with `,`; if string, use as-is with a deprecation warning. Verify: `backends.default: [kiro, claude]` resolves `GA_CREW_AGENT=kiro,claude`.

## 2. config/ghostship.yaml.example

- [ ] 2.1 Rewrite `config/ghostship.yaml.example` using the new nested structure. Include commented-out `- claude` and `- codex` under `backends.default`. Verify: `python3 -c "import yaml; yaml.safe_load(open('config/ghostship.yaml.example'))"` parses without error and spot-checks pass.

## 3. Tests

- [ ] 3.1 Update `tests/unit/test_yaml_config.py` — fix all path tuple references to new paths (e.g. `("crew", "git_author_name")` → `("crew", "git", "author", "name")`). Add tests for: deprecated path warning + value resolution; `backends.default` as list; `backends.default` as string (deprecated). Verify: `pytest tests/unit/test_yaml_config.py` passes.
- [ ] 3.2 Update `tests/unit/test_config.py` sync invariant — the `test_every_config_field_has_yaml_example_entry` test maps Config fields → env vars → `_KEY_MAP` → YAML paths → checks example. Verify: `pytest tests/unit/test_config.py -k yaml_example` passes.

## 4. Docs

- [ ] 4.1 Update `docs/configuration.md` — replace all old YAML key path references with new paths. Verify: no old paths (`crew.git_author_name`, `backends.agent`, `machine.memory`, etc.) remain in the doc.

## 5. Integration check

- [ ] 5.1 Run full unit suite and confirm no new failures. Verify: `pytest tests/unit/` exits 0 with no new failures beyond pre-existing.

## Workflow follow-up

- Commit to `release/0.8.0`, push to origin.
- Assimilate and archive after review.
