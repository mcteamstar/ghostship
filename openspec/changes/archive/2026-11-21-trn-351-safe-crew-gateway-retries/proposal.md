## Why

A successful liveness probe can currently cause a write to be replayed after a connection error. It establishes reachability but cannot establish whether the write was accepted. Generic 400 handling can also classify a rejected payload as stale credentials.

## What Changes

Use explicit gateway outcomes and operation-specific retry rules. Migrate Captain first, then apply the same rules to other side-effecting gateway operations.

## Capabilities

### Modified Capabilities

- `crew-lifecycle`: Classify authentication and transient failures and surface unknown write acceptance.

- `captain`: Preserve task identity when continuation is refused or acceptance is uncertain.

## Impact

CrewGatewayClient and caller error mapping, including Captain and MCP task operations. Depends on TRN-350.
