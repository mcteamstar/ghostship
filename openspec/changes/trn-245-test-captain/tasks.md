## 1. File scaffold

- [ ] 1.1 Create `tests/unit/test_captain.py` with module docstring, imports (`unittest`, `threading`, `from tests.fakes import FakePodmanClient`), and import of `transport.captain` helpers (following the same pattern as `test_sentinel.py`).

## 2. Cron-registry helpers

- [ ] 2.1 Add `TestCaptainJobs` — test `_captain_jobs` with dict payload (with `jobs` key), list payload, and non-list payload returns empty list.
- [ ] 2.2 Add `TestCaptainCheckinJob` — test `_captain_checkin_job` matching on name+agent, ignoring wrong agent (`"ghost"`), `enabled_only=True` filtering, and empty payload returns None.

## 3. Lock helpers

- [ ] 3.1 Add `TestCaptainOrderLock` — test that same `crew_id` returns same lock instance, different `crew_id` returns different lock, and returned type is `threading.Lock`.

## 4. Mailbox I/O helpers

- [ ] 4.1 Add `TestMailCount` — use `FakePodmanClient` catch-all `exec_checked_responses` to test Maildir two-number output (`"3 2"` → 5), single-number mbox output (`"7"` → 7), zero output (`"0 0"` → 0), and malformed non-numeric output → 0.
- [ ] 4.2 Add `TestReadAllMailCounts` — script `container_exec_checked` to return valid JSON `{"ghost": 3}` → dict with int; malformed JSON → empty dict; zero-count entries omitted.
- [ ] 4.3 Add `TestReadAllMailSubjects` — script `container_exec_checked` to return JSON mapping mailbox names to lists of subject dicts; assert return type is dict of lists.
- [ ] 4.4 Add `TestSkimAllMailboxes` — happy path: all 8 keys present (`ghost`, `spectre`, `banshee`, `wraith`, `reaper`, `raven`, `captain`, `admiral`); exec-failure fallback: `container_exec_checked` raises, fallback attempts `container_archive_get` per mailbox and returns empty lists rather than raising.

## 5. Order-template pipeline

- [ ] 5.1 Add `TestListOrderTemplates` — call with no `GA_ORDERS_DIR` override; assert result is non-empty list of 2-tuples; spot-check that `"sdd"` (or another stable built-in name) is present. Add `GA_ORDERS_DIR` pointing to missing path: assert one WARNING logged and result is non-empty (built-ins returned). Add `GA_ORDERS_DIR` pointing to `tmp_path` with a synthetic `.md` file whose stem matches a built-in: assert user description wins.
- [ ] 5.2 Add `TestLoadOrderTemplate` — call with a known built-in name (e.g. `"sdd"`); assert `(description, body)` tuple where body is non-empty string. Call with unknown name; assert `ValueError` raised.
- [ ] 5.3 Add `TestSubstitutePlaceholders` — test that `{{RAVEN_GATEWAY_ORIENTATION}}` is replaced with the constant's text; test that `{{UNKNOWN_TOKEN}}` triggers a WARNING log (use `assertLogs`).

## 6. _resolve_order_template

- [ ] 6.1 Add `TestResolveOrderTemplate` — create a minimal synthetic template file in `tmp_path` (or patch `_load_order_template` to return a controlled body) for each variant: `<change>` with valid `change_name` → name injected; `<change>` without `change_name` → ValueError; `<change?>` with name → name injected; `<change?>` without name → `"entire codebase"` injected; invalid `change_name` (uppercase) → ValueError; `template=None` → ValueError.

## 7. _captain_standing_view

- [ ] 7.1 Add `TestCaptainStandingView` — build a minimal job dict with `enabled=True`, call `_captain_standing_view` with a `FakePodmanClient` scripted to return `"2 0"` for mail-count exec; assert required keys present and `status == "enabled"`. Repeat with `enabled=False` → `status == "paused"`. Set `registry._reg["crews"]["test-crew"]["schedules"]` with a captain entry containing `last_checkin_at` and `current_task_id`; assert those values appear in result.

## 8. _append_captain_mail I/O path

- [ ] 8.1 Add `TestAppendCaptainMail` — patch `_read_crew_secret` to return `None` (no signing secret); call `_append_captain_mail` with a `FakePodmanClient`; assert `container_exec_checked` was called and the command contains a base64 string; decode it and assert no `X-Admiral-Sig` header. Patch `_read_crew_secret` to return a valid 32-byte hex seed; assert decoded mail contains `X-Admiral-Sig:`. Set `registry._reg["crews"]["test-crew"]["last_captain_message_id"]` to a prior message ID; assert decoded mail contains `Supersedes:` referencing it.

## 9. Verify

- [ ] 9.1 Run `python -m pytest tests/unit/test_captain.py -v` from the repo root; confirm all new tests pass with no failures or errors.
- [ ] 9.2 Run the full unit suite `python -m pytest tests/unit/ -v` to confirm no regressions in existing tests.
