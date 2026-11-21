## 1. Map the existing contracts

- [ ] 1.1 Capture a strict OpenSpec baseline of capability paths, requirement titles, and scenarios. Complete the old-to-new inventory for whole-spec moves and requirement splits, checking active deltas, docs, and tooling for old capability IDs or path assumptions.
- [ ] 1.2 Identify conflicting or overlapping requirements in the mixed specs. Record unresolved conflicts explicitly and preserve all distinct contracts and scenarios in the migration.

## 2. Migrate and verify

- [ ] 2.1 Move cohesive specs and split mixed requirement blocks into the agreed nested ownership tree. Check that every original requirement and scenario maps to a destination and old owners retain only requirements they still own.
- [ ] 2.2 Update active delta paths, affected proposal capability IDs and maintained references. Verify TRN-328 still resolves its target specs. Preserve historical archives.
- [ ] 2.3 Run strict validation on the full spec tree and active changes. Confirm nested discovery and verify a nested delta sync and archive in a disposable store. Run the Sweepy/OpenSpec workflow checks and compare requirement and scenario text against the baseline.
