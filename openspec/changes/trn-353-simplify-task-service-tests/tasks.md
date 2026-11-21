## 1. Simplify service tests

- [x] 1.1 Add a reusable test fixture that constructs a fresh TaskService with injectable gateway, mailbox and registry collaborators.
- [x] 1.2 Consolidate batch dispatch and pickup assertions by outcome. Preserve partial registry writes, lost members, timeout and mail wakeup, task identity and timestamp expiry.
- [x] 1.3 Exercise steer paths directly through TaskService and move slot-routing coverage beside task tests. Preserve wire call ordering and failure surfaces.

## 2. Verify compatibility

- [x] 2.1 Focus MCP adapter tests on schema, forwarding and error compatibility. Keep the shared-instance wiring assertion and registry integration coverage.
- [x] 2.2 Run unit and gateway integration suites separately, then run the existing Corsair E2E suites to verify live dispatch, pickup and steer. Confirm the implementation diff is limited to tests and change artifacts.
