# TRN-297 — Tasks

## T1 — Create start_main.py

- [ ] 1.1 Read current `bin/start.sh` and `bin/lib/start_ops.py` in full
- [ ] 1.2 Read `bin/lib/install_main.py` for structural reference
- [ ] 1.3 Create `bin/lib/start_main.py` — config resolution, podman start, compose up, health check
- [ ] 1.4 Verify compose env is built as an explicit dict (no eval, no string interpolation)

## T2 — Reduce start.sh to thin shim

- [ ] 2.1 Rewrite `bin/start.sh` as prereq check + `exec python3 bin/lib/start_main.py "$@"`
- [ ] 2.2 Verify `bash -n bin/start.sh` passes
- [ ] 2.3 Verify `wc -l bin/start.sh` ≤ 40
- [ ] 2.4 Verify `grep -c eval bin/start.sh` = 0

## T3 — Tests

- [ ] 3.1 Create `tests/unit/test_start_main.py` — mock podman_setup, compose subprocess, health check
- [ ] 3.2 Cover: successful start, podman already running, compose up failure, health check timeout
- [ ] 3.3 Verify `pytest tests/unit/test_start_main.py` passes

## T4 — Integration verification

- [ ] 4.1 Run `ghostship upgrade` on corsair — succeeds
- [ ] 4.2 Run `scripts/run.sh --e2e` — 23 passed
- [ ] 4.3 Check off all tasks and commit
