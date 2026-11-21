## Context

The Identity Center credential-route class inherits another suite to reuse setup and then disables 18 inherited test methods dynamically.

## Decisions

Extract setup for pending flows, credential stores, registry records, and captured propagation into fixtures. Keep each test's mutable state isolated and restore backend flow objects after each case. Parameterize only equivalent backend outcomes and retain dedicated Identity Center profile-wait coverage. Build on TRN-354's HTTP and ASGI test fixtures.

Move the completion harness into a fixture or setup-only base with no collected tests. Give each case fresh pending flow state, credential store, registry, and propagation recorder. Restore exact previous singleton state and patched collaborators even if setup or assertions fail. Keep a mapping of old outcomes to replacement cases before removing the dynamic suppression.

## Risks / Trade-offs

Shared fixtures can conceal backend differences or leak pending login state. Assert backend and profile targeting in each case and check isolated collection.
