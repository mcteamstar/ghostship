## Context

See `proposal.md – Why` for motivation.

`transport/captain.py` is a pure-computation + thin-I/O module: most helpers
take explicit arguments (no global HTTP state, no Starlette Request objects) and
can be tested with the existing `FakePodmanClient`. The only I/O path is
`container_exec_checked` (used by `_mail_count` and `_append_captain_mail`) and
`container_archive_get` (used by the sentinel helpers, already tested in
`test_sentinel.py`). `conftest.py` already blocks registry file I/O for all unit
tests via `_block_registry_io`.

The order-template functions (`_load_order_template`, `_list_order_templates`)
read from the filesystem. In the test environment the academy `orders/` directory
is present under the repo root, so those functions work without mocking. For
`GA_ORDERS_DIR` override tests a `tmp_path` fixture is sufficient.

The three `_captain_do_*` dispatcher functions live in `server.py` (pending
trn-242 refactor) and depend heavily on HTTP clients and live crew state — they
are deliberately excluded from this change and covered by the
`transport-test-coverage` spec's `_captain_do_order/status/stop branch test coverage`
requirement which targets a future task.

```
transport/captain.py
│
├── Pure computation (no I/O)
│   ├── _captain_jobs / _captain_checkin_job    ← new tests
│   ├── _captain_order_lock                      ← new tests
│   ├── _parse_order_front_matter               ← existing tests
│   ├── _substitute_placeholders                 ← new tests
│   ├── _validate_captain_change_name            ← existing tests
│   ├── _resolve_order_template                  ← new tests
│   ├── _parse_sentinel_file                     ← existing tests
│   └── _format_captain_mail                     ← existing tests
│
├── Filesystem I/O (orders dir)
│   ├── _list_order_templates                    ← new tests
│   └── _load_order_template                     ← new tests
│
└── Container I/O (FakePodmanClient)
    ├── _mail_count                              ← new tests
    ├── _read_all_mail_counts                    ← new tests
    ├── _read_all_mail_subjects                  ← new tests
    ├── _skim_all_mailboxes                      ← new tests
    ├── _captain_standing_view                   ← new tests
    ├── _read_sentinel_file                      ← existing tests
    ├── _delete_sentinel_file                    ← existing tests
    └── _append_captain_mail                     ← new tests
```

## Goals / Non-Goals

**Goals:**
- Unit tests for all untested helpers in `transport/captain.py` using
  `FakePodmanClient` and `tmp_path`; no production code changes.
- Tests run in the existing `tests/unit/` suite under `pytest` with no
  additional dependencies.
- All new tests pass in the current checkout (no real Podman required).

**Non-Goals:**
- `_captain_do_order`, `_captain_do_status`, `_captain_do_stop` — these live in
  `server.py` and require live HTTP / registry scaffolding; deferred to a
  follow-on task per the transport-test-coverage spec.
- `_captain_monitor` — lives in `monitors.py`; already specified separately in
  the transport-test-coverage spec.
- Integration or e2e tests.

## Decisions

**D1 — single new file `tests/unit/test_captain.py`**

All new tests go into one file rather than appending to `test_sentinel.py`.
`test_sentinel.py` was written specifically for TRN-243 sentinel/mail helpers.
A dedicated `test_captain.py` keeps the scheduling, cron-registry, mailbox-I/O,
and template-pipeline tests together and avoids bloating the sentinel file.

Alternative: append to `test_sentinel.py`. Rejected — mixing concerns makes
future navigation and the trn-242 refactor review harder.

**D2 — `FakePodmanClient.set_exec_checked_response` for `_mail_count`**

`_mail_count` calls `container_exec_checked` with a `sh -c` script. The fake's
`set_exec_checked_response` key format is `"<container>:<cmd_joined>"`, which
matches when the full command list is joined with `:`. For `_mail_count` the key
becomes `"gs-crew:sh:-c:<script>:--:<mailbox_path>"`. Tests will use
`podman.exec_checked_responses["gs-crew"] = "3 2"` (catch-all by container)
rather than hard-coding the full script string — this avoids brittle coupling to
the exact script text.

**D3 — real `orders/` directory for template tests**

`_load_order_template` and `_list_order_templates` resolve the orders directory
via `_resolve_orders_dir()`, which checks `_ORDERS_CONTAINER_DIR`
(`/orders`) first, then falls back to the repo-relative `academy/orders/`.
In the test environment `/orders` does not exist, so the fallback fires and the
real templates are readable. Tests can assert on the known built-in template
names without mocking filesystem calls. For `GA_ORDERS_DIR` override tests,
a `tmp_path` directory with synthetic `.md` files is sufficient.

**D4 — `_captain_standing_view` tested with patched registry**

`_captain_standing_view` reads `registry._reg` inside a `with registry:` block.
The `_block_registry_io` autouse fixture in `conftest.py` already patches
`_load_registry` and `_save_registry`, but `registry._reg` starts as `{}`.
Tests that need `last_checkin_at` / `current_task_id` will set
`registry._reg["crews"]["test-crew"]["schedules"]` directly before calling the
function. This avoids adding new fixtures and keeps the test self-contained.

## Risks / Trade-offs

- [Risk] `_mail_count` shell script changes break test key matching →
  Mitigation: use catch-all container key (`podman.exec_checked_responses["gs-crew"]`)
  rather than the full script key; tests assert on return value, not call args.
- [Risk] `_list_order_templates` enumerates real `academy/orders/` files; a
  future rename of a built-in template breaks the assert →
  Mitigation: assert `len(result) > 0` and spot-check one known stable template
  name (e.g. `"sdd"`); avoid asserting on exact count.
- [Risk] `_substitute_placeholders` embeds large constant strings; test for
  residual placeholder warning requires a custom template body →
  Mitigation: construct a minimal body `"{{UNKNOWN}}"` directly in the test
  rather than using a real template file.
