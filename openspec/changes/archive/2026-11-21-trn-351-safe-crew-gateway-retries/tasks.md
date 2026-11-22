## 1. Make gateway recovery operation-aware

- [x] 1.1 After TRN-350 lands, map supported gateway rejection codes and define a bounded policy for each gateway operation.
- [x] 1.2 Migrate Captain first and then other recovering callers. Surface uncertain write acceptance and preserve accepted IDs and compatible external responses.
- [x] 1.3 Test stale credentials, busy and malformed replies, rejected payloads, and dropped responses after a write. Assert that no second spawn or continuation is sent when acceptance is unknown.
- [x] 1.4 Verify late Raven restore failure and reconciliation on Corsair with an accepted task already in the roster.

  Corsair replayed the recorded late restore failure `6a7021fd0f5bff93` using an isolated schedule fixture against the live gateway. Replacement Raven `ac466477489d6f6e` confirmed the existing Ghost task `4fec341ae4b7a674` completed. The live roster gained only the replacement Raven, and a check-in during recovery sent no second write.
- [x] 1.5 Verify that with the supported gateway, which exposes no reliable attempt correlation for Captain writes, unknown acceptance retains an operator-visible hold across ticks without another write. Exercise positive adoption only if a supported wire contract exposes such correlation.
