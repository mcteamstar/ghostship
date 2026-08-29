# TRN-69 Tasks — Captain Escalation Deduplication

**IMPORTANT: This change is in `transport/server.py` only. Do NOT touch `academy/steering/STANDING_ORDERS.md`, `academy/orders/sdd.md`, or any documentation file. The only file that needs editing is `transport/server.py`.**

## Section 1: Transport changes (transport/server.py ONLY)

- [ ] 1.1 **Update `_RAVEN_SELF_CANCEL`** (~line 1191 in `transport/server.py`).

  Find this string constant:
  ```python
  _RAVEN_SELF_CANCEL = """Once you're genuinely satisfied the standing orders are met, pause your own check-in job (named "captain", the only one in this crew) through the CLI, and confirm via `cron list` that it actually stopped before you hold — don't ask the Admiral to do it for you, and don't report it done without checking."""
  ```

  Replace with:
  ```python
  _RAVEN_SELF_CANCEL = """Once you're genuinely satisfied the standing orders are met — including after you have sent a completion report to the Admiral for a one-shot monitoring task — pause your own check-in job (named "captain", the only one in this crew) through the CLI, and confirm via `cron list` that it actually stopped before you hold. Do not ask the Admiral to do it for you, and do not report it done without checking.

  For monitoring orders (watch a task, report when done): the standing order is satisfied the moment you send the completion report to the Admiral. Pause the cron immediately after sending — do not wait for a further instruction or the next cycle."""
  ```

- [ ] 1.2 **Update `_CAPTAIN_CHECKIN_TASK`** (~line 1256 in `transport/server.py`).

  Find the paragraph that begins:
  ```
  First read /var/mail/captain and identify orders that are new since your prior check-in.
  ```

  After that paragraph (and before the `{_RAVEN_GATEWAY_ORIENTATION}` line), insert a new paragraph:
  ```
  Before sending any report to the Admiral about a completed task, check the Admiral mailbox at /var/mail/admiral/ (both new/ and cur/) for a prior message whose Subject line references the same task ID. If a prior report for that task already exists, do not send another one — instead treat the standing order as satisfied and pause the cron.
  ```

## Section 2: Tests

- [ ] 2.1 In `tests/unit/test_transport.py`, add a test asserting `_RAVEN_SELF_CANCEL` contains the phrase "completion report".

- [ ] 2.2 In `tests/unit/test_transport.py`, add a test asserting `_CAPTAIN_CHECKIN_TASK` contains the substring "/var/mail/admiral".

  Run `python -m pytest tests/ -x -q` to verify all tests pass.

## Section 3: Docs

- [ ] 3.1 Update `docs/architecture.md` — add one sentence under the Captain section noting that monitoring standing orders self-pause after the first completion report is sent.

## Section 4: Integration verification

- [ ] 4.1 Manual check after deploy: launch a crew, set a monitoring captain order, let it complete, count admiral mails after 3 cron cycles. Expected ≤2. This step is NOT required for the commit — just note it as a post-deploy check.

  Commit message: `fix: TRN-69 — captain dedup: report-and-pause + admiral mail check`
