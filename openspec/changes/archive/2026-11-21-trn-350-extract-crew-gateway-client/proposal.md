## Why

Crew gateway HTTP calls, cookie handling, wire errors and recovery live in lifecycle.py and are shared by tools, Captain and monitors through private imports.

## What Changes

Extract CrewGatewayClient behind the existing lifecycle entry points. Preserve current behavior and prove the wire contract using the installed HTTP client.

## Capabilities

No behavior contract changes. TRN-351 owns retry policy changes.

## Impact

Transport lifecycle, assembly and gateway tests. Existing MCP, HTTP and resource contracts stay stable.
