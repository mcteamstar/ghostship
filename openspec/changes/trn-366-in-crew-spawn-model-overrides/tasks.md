# Tasks

## 1. Add model selection to the in-crew helper

- [x] 1.1 Extend named dispatch parsing and payload construction with optional `--model <id>`, mirroring the transport's 500-character format bounds; update helper unit coverage for valid, omitted, missing, empty, malformed, overlong, and non-dispatch cases, and verify `tests/unit/test_ghostship_spawn.py` passes.
- [x] 1.2 Document the dispatch option and a stdin-based usage example in the `ghostship-spawn` skill, and assert the option in its skill contract test; verify `tests/unit/test_ghostship_spawn.py` passes.

## 2. Teach Raven to use requested models

- [x] 2.1 Update Raven's gateway orientation in `academy/agents/raven.json` and `transport/captain.py` to tell Raven to pass an explicitly requested model with `--model`, and extend the consistency assertion; verify `tests/unit/test_raven_prompt_consistency.py` and `tests/unit/test_raven_prompt_contract.py` pass.

## 3. Verify the packaged helper

- [ ] 3.1 Build a disposable crew image and dispatch a named persona with a valid model override; verify the new task's `--status` output shows the requested model.

## Workflow follow-up

- Rebuild and roll out the crew image before using this helper in existing crews; running crews retain their current helper until recreated.
