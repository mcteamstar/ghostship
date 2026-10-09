# Tasks: TRN-206

## 1. Fix _RAVEN_GATEWAY_ORIENTATION

- [x] 1.1 In `transport/captain.py`, find `_RAVEN_GATEWAY_ORIENTATION` (~line 53)
- [x] 1.2 In the spawn auth instruction, add `, X-Session-Key: $KIRO_SESSION_ID` alongside
  the existing `X-Internal-Secret` header instruction so it reads:
  `authenticating each request with ... X-Internal-Secret header ... and X-Session-Key: $KIRO_SESSION_ID`
- [x] 1.3 Verify the SDD template still has its own explicit instruction (it should be
  redundant after this fix but harmless to keep)

## 2. Test

- [x] 2.1 Run unit tests: `bash tests/run.sh --unit`
- [ ] 2.2 Verify free-form captain order can dispatch a persona (smoke test on starport)
