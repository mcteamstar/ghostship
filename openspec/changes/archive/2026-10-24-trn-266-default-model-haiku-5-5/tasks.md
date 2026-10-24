# Tasks: trn-266-default-model-haiku-5-5

## 1. Per-agent JSON files

- [x] 1.1 In `academy/agents/ghost.json`, change `"model": "gpt-5.6-luna"` → `"model": "claude-haiku-5-5"`. Verify: `grep '"model"' academy/agents/ghost.json` shows `claude-haiku-5-5`.
- [x] 1.2 In `academy/agents/spectre.json`, same change. Verify same way.
- [x] 1.3 In `academy/agents/banshee.json`, same change. Verify same way.
- [x] 1.4 In `academy/agents/reaper.json`, same change. Verify same way.
- [x] 1.5 In `academy/agents/wraith.json`, same change. Verify same way.
- [x] 1.6 In `academy/agents/raven.json`, same change. Verify same way.
- [x] 1.7 Confirm: `grep -r '"model": "gpt-5.6-luna"' academy/agents/` returns no results.

## 2. Config example

- [x] 2.1 In `config/ghostship.yaml.example`, set `model.default: "claude-haiku-5-5"` (was `""`). Verify: `grep 'default:' config/ghostship.yaml.example` shows `claude-haiku-5-5`.

## 3. README.md

- [x] 3.1 Update both occurrences of `gpt-5.6-luna` in `README.md` to `claude-haiku-5-5`. Verify: `grep gpt-5.6-luna README.md` returns no results.

## 4. docs/configuration.md

- [x] 4.1 Update any scenario/example reference to `gpt-5.6-luna` in `docs/configuration.md` to `claude-haiku-5-5`. Verify: `grep gpt-5.6-luna docs/configuration.md` returns no results.

## 5. Verification

- [x] 5.1 `grep -r 'gpt-5.6-luna' academy/ config/ README.md docs/configuration.md` returns no results.
- [x] 5.2 Run unit tests: `pytest tests/unit/ -q` — no failures. (Model strings in test fixtures don't need updating unless they assert `gpt-5.6-luna` specifically — check `grep -r 'gpt-5.6-luna' tests/`.)
