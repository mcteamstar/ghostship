## MODIFIED Requirements

### Requirement: Test suite runs safely inside crew containers

The test suite SHALL be partitioned into Podman-dependent tests and pure unit
tests. Tests that require a real Podman socket SHALL be decorated with
`@unittest.skipUnless(shutil.which("podman"), "requires podman")` so they are
skipped automatically when Podman is not available (e.g., inside a crew
container). The top of the relocated test module (formerly
`transport/test_transport.py`, now living under `tests/` per the
`test-orchestration` capability) SHALL continue to document which test
classes are Podman-dependent and which are safe to run anywhere, and its
dual import-resolution shim (package-style `transport.server` import vs. a
flat-import fallback) SHALL be reconciled against the new location rather
than left to depend on which of the two branches happens to still resolve.

#### Scenario: Full suite completes inside a crew container
- **WHEN** the relocated test suite's unit-category tests are run inside a crew container where Podman is absent
- **THEN** Podman-dependent tests are skipped, all other tests run and pass, and the suite exits 0

#### Scenario: Full suite runs all tests on a host with Podman
- **WHEN** the relocated test suite's unit and integration categories are run on a host where Podman is available
- **THEN** all tests including Podman-dependent ones are executed

#### Scenario: Server module still importable after relocation
- **WHEN** the relocated test suite imports the transport server module
- **THEN** exactly one of the two existing import strategies (package-style `transport.server`, or the flat fallback) resolves correctly and deterministically from the new location — not by accident of which directory happens to be on `sys.path` for a given invocation
