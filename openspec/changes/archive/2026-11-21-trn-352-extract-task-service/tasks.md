## 1. Extract task operations

- [x] 1.1 After TRN-351 lands, inventory callers and characterize dispatch, pickup and steer contracts before moving them.
- [x] 1.2 Move single and batch dispatch, steer, pickup, and timestamps to TaskService. Reuse existing crew, gateway, and registry dependencies.
- [x] 1.3 Route MCP tools through the service and remove duplicate internal paths once callers are migrated. Verify tool schemas and response compatibility.
- [x] 1.4 Use a stateful fake gateway to verify partial batch acceptance, lost tasks, mail wakeups, and task identity across dispatch, pickup and steer.
- [x] 1.5 Assert that dispatch timestamps are visible through single and batch pickup, that completed entries expire, and that adapters and compatibility wrappers share one service instance.
