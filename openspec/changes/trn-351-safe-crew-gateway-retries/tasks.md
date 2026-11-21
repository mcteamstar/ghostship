## 1. Make gateway recovery operation-aware

- [ ] 1.1 After TRN-350 lands, map supported gateway rejection codes and define a bounded policy for each gateway operation.
- [ ] 1.2 Migrate Captain first and then other recovering callers. Surface uncertain write acceptance and preserve accepted IDs and compatible external responses.
- [ ] 1.3 Test stale credentials, busy and malformed replies, rejected payloads, and dropped responses after a write. Assert that no second spawn or continuation is sent when acceptance is unknown.
- [ ] 1.4 Verify late Raven restore failure and reconciliation on Corsair with an accepted task already in the roster.
- [ ] 1.5 Test adoption when exactly one accepted task matches the attempt identifier. Test that missing, ambiguous, and unsupported correlation leave the operator-visible hold in place across ticks without another write.
