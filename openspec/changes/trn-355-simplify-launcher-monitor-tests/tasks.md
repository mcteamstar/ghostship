## 1. Implementation and verification

- [ ] 1.1 Consolidate same-crew election cases with bounded event handshakes that observe waiter entry before releasing the leader. Keep distinct leader failure, healthy early exit, memory checks, and cross-crew admission cases.
- [ ] 1.2 Extract one internal tick per monitor. Preserve first-tick timing, Captain's dynamic next wakeup, exception boundaries, registry updates, and lock scope. Keep a focused loop test for cadence instead of driving every behavior through sleep.
- [ ] 1.3 Test schedule advancement without replay after uncertain writes, idle fail-open and concurrent wake protection, and Captain handling of paused or stopped crews and completion. Run focused lifecycle and monitor suites and the full unit suite.
