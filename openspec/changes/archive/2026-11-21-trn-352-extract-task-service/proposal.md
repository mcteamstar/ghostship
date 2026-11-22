## Why

Task operations are split across MCP tools, lifecycle helpers and module globals, making partial results and task state difficult to test as one flow.

## What Changes

Extract TaskService for dispatch, batch admission, pickup and steer. Keep existing API contracts and reuse the registry and gateway client.

## Capabilities

No behavior contract changes.

## Impact

Transport task operations, MCP adapters and task tests. Depends on TRN-351.
