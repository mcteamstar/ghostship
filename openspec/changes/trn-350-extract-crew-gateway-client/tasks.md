## 1. Extract the gateway boundary

- [ ] 1.1 Characterize authenticated headers, wire parsing, redacted errors and retry behavior with the installed HTTP client and an injected test transport.
- [ ] 1.2 Extract CrewGatewayClient and wire its dependencies at application assembly. Preserve lifecycle entry points and the one-shot provisioning path.
- [ ] 1.3 Verify both local and container imports, existing tool and HTTP responses, and absence of gateway recovery lock re-entry during crew startup.
- [ ] 1.4 Exercise a recovery call that invokes crew restoration, which itself makes a one-shot gateway request. Assert completion within a bounded deadline and that compatibility and migrated callers share the same per-crew recovery lock.
