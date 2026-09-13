# transport-test-coverage — Delta Spec (trn-160-files-streaming-tests)

## ADDED Requirements

### Requirement: Streaming transfer classes have test coverage

`_ResponseChunkReader` and `_TarMemberStream` in `transport/files.py` SHALL have unit tests covering: normal reads, cross-chunk-boundary reads, empty stream, missing tar member (raises ValueError), truncated/invalid archive (raises), close idempotency, and context manager protocol.

#### Scenario: ResponseChunkReader reads across chunk boundaries
- **WHEN** a `_ResponseChunkReader` is constructed from multiple small chunks
- **THEN** `read(n)` returns exactly n bytes assembled correctly across chunk boundaries

#### Scenario: TarMemberStream raises on missing member
- **WHEN** a `_TarMemberStream` is constructed with an `expected_path` that is not present in the archive
- **THEN** a `ValueError` is raised at construction time

#### Scenario: _transfer_upload slash-ref workaround is exercised
- **WHEN** `_transfer_upload` is called and `git rev-parse HEAD` fails (empty working tree after clone)
- **THEN** `git checkout -b <branch> origin/<branch>` is called to check out the first available remote branch
