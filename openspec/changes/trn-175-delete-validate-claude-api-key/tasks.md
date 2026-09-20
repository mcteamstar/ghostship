## 1. Delete dead helper and fix no-op body

- [ ] 1.1 In `transport/config.py`, delete the `_validate_claude_api_key` function (the empty-body private helper, ~L85–97)
- [ ] 1.2 Replace the body of `Config.validate()` with `pass` and update its docstring to: "No-op. Retained for call-site compatibility. Credential validation is lazy — deferred to `launch()` time."

## 2. Fix stale startup comment

- [ ] 2.1 In `transport/server.py`, find the comment near the `cfg.validate()` call at startup (~L4187) that claims "Raises ConfigError if GA_CREW_ACP_BACKEND=claude and GA_CREW_ANTHROPIC_API_KEY is unset"
- [ ] 2.2 Replace that comment with: "No-op — credential validation is lazy (deferred to launch())"

## 3. Verify tests pass

- [ ] 3.1 Run the unit test suite: `bash tests/run.sh --unit`. All existing `validate()` tests should pass without modification (they assert it does not raise, which remains true with a `pass` body)
- [ ] 3.2 Confirm no test references `_validate_claude_api_key` directly (it should not — grep to verify)
