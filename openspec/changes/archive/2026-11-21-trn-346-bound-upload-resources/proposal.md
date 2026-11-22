## Why

TRN-345 confines uploads to the crew workspace and stages archive and bundle output before publication. The upload handler still buffers the entire request, and wire size alone does not bound extraction or checkout work.

## What Changes

Bound request ingestion, archive expansion, and bundle storage, report limit errors consistently, and clean up temporary data.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `file-transfer`

## Impact

Transport, operator configuration and focused tests.
