## 1. Transport — crews() handler

- [x] 1.1 In `_crews()` (transport/server.py), remove `"last_tool"` from both agent list comprehensions (the `isinstance(tasks, list)` and `isinstance(tasks, dict)` branches)
- [x] 1.2 Add `uptime_secs` to running crew entries: call `podman.container_inspect(info["container"])`, parse `State.StartedAt` as a UTC datetime, compute `int((datetime.now(UTC) - started_at).total_seconds())`, and add to the crew entry; wrap in try/except and omit the field (or set null) on failure
- [x] 1.3 Confirm `last_task_at` is already included in the entry (it is — TRN-89); no change needed unless null-handling needs to be explicit

## 2. MCP tool docstring

- [x] 2.1 Update the `crews` MCP tool docstring to document the new response shape: remove mention of `last_tool`, add `last_task_at`, `uptime_secs`

## 3. Skill update

- [x] 3.1 Update `.claude-plugin/skills/ghostship-command/SKILL.md` — revise guidance on `crews` output to reflect removed `last_tool` and added `uptime_secs`; reinforce that `pickup` is the tool for live task detail

## 4. Tests

- [x] 4.1 Update any test assertions in `tests/` that check for `last_tool` in `crews()` response — remove those assertions
- [x] 4.2 Add assertions verifying `last_tool` is absent from agent entries in `crews()` response
- [x] 4.3 Add assertions verifying `uptime_secs` is present (integer) for a running crew and absent (or null) for a stopped crew
- [x] 4.4 Run `tests/run.sh --unit` and confirm all tests pass
