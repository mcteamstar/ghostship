## Context

The baseline has 85 live specs and all pass strict validation under OpenSpec 2.0.0. Successful discovery includes paths such as `captain/independent-review`, `auth/credential-profiles`, and `installation/client-only`. TRN-328 currently targets `transport/caddy-proxy` and `transport/dashboard-proxy` in active deltas.

## Decisions

Use ownership to determine where a requirement lives. Use one canonical owner per contract, retaining distinct requirement blocks where overlap has yet to be resolved. Preserve scenario text and existing requirement names during moves unless the implementation plan documents a mechanical heading or reference correction. Keep unresolved conflicts visible for later spec reconciliation.

| Area | Proposed ownership |
| --- | --- |
| Crew lifecycle | Provisioning, startup, capacity and idle behavior under `crew-lifecycle/`. Registry persistence and reconciliation belong with `registry/`, and wire recovery belongs under `transport/crew-gateway/`. |
| Task operations | Dispatch, slots, batch, pickup, steer, and timestamps under `task-orchestration/`. Recurring task schedule behavior gets a scheduling leaf. Move Captain-specific check-ins out of the general task spec. |
| Captain | Runtime, Raven and standing orders under the existing `captain/` tree. Put free will next to the existing named orders. |
| Credentials | Backend login, storage, profiles, resolution, and propagation under `auth/`. Keep Admiral signing and Transport portal authentication with their own owners. |
| File transfer | Supply, evac, and transfer security under `file-transfer/`. Preserve cross-cutting security contracts with their existing owners where they apply outside transfer. |
| Tests and installation | Group test expectations by subsystem under `testing/`. Keep the existing `installation/` subtree and use it for install-specific contracts. |

Maintain a migration inventory keyed by old capability path and, for splits, by requirement heading. Record the new owner, reference updates, and any unresolved overlap. Keep edits to main specs and corresponding active deltas together. Leave active TRN-328 paths where sensible or retarget its deltas and references in the same migration. Preserve archive directories and their spec snapshots.

Verify the repository's actual path consumers, including OpenSpec CLI discovery, strict validation, and the shipped Sweepy workflow. Exercise a nested delta through sync and archive using a disposable store to detect path flattening or accidental recreation of old owners. Compare the before-and-after requirement and scenario inventory by text, excluding only documented reference edits.

## Risks / Trade-offs

Capability path changes can orphan deltas or make old specs reappear on sync. Deep nesting also makes browsing harder when the folders do not represent real ownership. Prefer shallow groups and keep a map through the migration. For the six consolidation areas recorded in the migration inventory, use current runtime contracts to correct stale wording and preserve distinct scenarios. Record any other unresolved policy conflict for follow-up.
