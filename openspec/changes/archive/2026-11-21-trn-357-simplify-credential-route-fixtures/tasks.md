## 1. Implementation and verification

- [x] 1.1 Replace test-class inheritance and dynamic suppression with a setup-only fixture. Restore original flow state after each case and keep credential, registry, and timing fixtures local.
- [x] 1.2 Consolidate equivalent backend cases after checking original coverage. Preserve separate cancellation between poll and commit, storage failure and retry, propagation failure after commit, profile isolation, and Identity Center pending, later success, expiry, and nonblocking capture behavior.
- [x] 1.3 Verify collection exposes Identity Center cases once and run them both standalone and with credential route, login, and auth tests. Run the full unit suite after TRN-354 and check that pending flows do not leak between cases.
