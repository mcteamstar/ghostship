## Why

The upload handler buffers the entire request, and wire size alone does not bound extraction or checkout work.

## What Changes

Bound request ingestion and archive expansion, report limit errors consistently, and clean up temporary data.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `file-transfer`

## Impact

Transport, operator configuration and focused tests.
