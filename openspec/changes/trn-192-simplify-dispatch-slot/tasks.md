# TRN-192 Tasks

## 1. Simplify `_resolve_dispatch_slot` in `transport/lifecycle.py`

- [ ] 1.1 Remove the `slot is True` UUID-generation branch
- [ ] 1.2 Remove the `isinstance(slot, str)` named-slot branch (covers both
  `"bridge"` and arbitrary names)
- [ ] 1.3 Resulting logic: enrolled agent → member slot; unenrolled or
  `slot=None` → headless `(None, None)`
- [ ] 1.4 Confirm batch dispatch `_dispatch_batch` uses the same helper and
  is covered by the simplification

## 2. Update `dispatch()` MCP tool in `transport/server.py`

- [ ] 2.1 Change `slot` param type annotation from `str | bool | None` to
  `bool | None`
- [ ] 2.2 Update docstring: remove UUID/named/bridge documentation, document
  the two remaining modes
- [ ] 2.3 Remove the `slot_pre_create` logic that POSTs to `/api/chat/slots`
  before dispatch (only needed for named/UUID slots — member slots are
  pre-created at enrollment)

## 3. Update tests in `tests/unit/test_dispatch_slot.py`

- [ ] 3.1 Remove tests for `slot=True` UUID path
- [ ] 3.2 Remove tests for named slot path (`slot="bridge"`, `slot="myname"`)
- [ ] 3.3 Ensure enrolled-agent and headless tests still pass

## 4. Update documentation

- [ ] 4.1 `README.md` — update `dispatch` tool table: remove slot=True and
  named slot rows
- [ ] 4.2 `.claude-plugin/skills/ghostship-command/SKILL.md` — update slot
  guidance to reflect two modes only

## 5. Verify

- [ ] 5.1 Run full unit test suite
- [ ] 5.2 Deploy to academy, dispatch a ghost with no slot (member), confirm
  attested and visible in dashboard
- [ ] 5.3 Dispatch a ghost with `slot=None` (headless), confirm attested and
  no session created
