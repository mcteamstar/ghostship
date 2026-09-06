# Delta Spec: file-transfer — force re-seed via supply (TRN-109)

## Changes to Requirement: Supplying files and archives via supply

### Added scenario: Force re-seed a bundle into an occupied destination

The `supply` tool SHALL accept an optional `force: bool = False` parameter. When `force=True` and `bundle=True`, the system SHALL remove the existing destination path inside the crew workspace before cloning, allowing a previously-seeded path to be replaced with an updated bundle.

#### Scenario: Force re-seed replaces existing destination
- **WHEN** `supply` is called with `bundle=True`, `force=True`, and a destination `path` that already exists and is non-empty in the crew's workspace
- **THEN** the system removes the existing destination, clones the uploaded bundle into that path, and returns success

#### Scenario: Default behaviour (force=False) still rejects occupied destination
- **WHEN** `supply` is called with `bundle=True` and `force=False` (the default) and the destination path already exists and is non-empty
- **THEN** the clone fails and the existing destination is left unchanged (existing behaviour, no change)

#### Scenario: force=True is a no-op for non-bundle modes
- **WHEN** `supply` is called with `force=True` and `bundle=False`
- **THEN** the `force` parameter has no effect; the upload proceeds as a normal plain file write or tar unpack

## Changes to Requirement: Presigned URL expiry and integrity

The HMAC payload for `supply` presigned upload URLs SHALL include the `force` flag alongside the existing `bundle` and `unpack` flags. A token signed with `force=False` SHALL be rejected if presented in a context that would trigger `force=True` behaviour, and vice versa.

#### Scenario: Token signed without force cannot be replayed as a force operation
- **WHEN** a presigned upload URL was generated with `force=False`
- **THEN** the HMAC verification rejects any attempt to interpret that token as authorising a pre-clone deletion
