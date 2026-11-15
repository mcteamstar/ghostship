# Tasks

## 1. Inventory public and persisted surfaces

- [x] 1.1 Trace MCP launch arguments and resource registrations; record current schemas, URIs, metadata, errors, and available alias mechanisms in `compatibility-matrix.md`, verifying each entry against source and relevant OpenSpec requirements.
- [x] 1.2 Trace crew listing/API payloads, Radar display, and persisted registry fields; record consumers and migration risks in the matrix, verifying the inventory against source, tests, and API specs.
- [x] 1.3 Trace configuration, manifests, policy naming, docs, agent instructions, and CLI surfaces; classify each as public, persisted, or internal and verify each current name against source/docs (record when no CLI launch surface exists).

## 2. Assess alias and migration behavior

- [x] 2.1 Evaluate `comp` plus legacy `composition` launch argument handling, including both-equal and conflicting inputs; document schema compatibility and a recommendation in the matrix, verified against the current MCP framework and client-facing tool schema.
- [x] 2.2 Evaluate `transport://comps` alongside `transport://compositions`; document URI discoverability, alias registration options, and client migration risk, verified against the current resource registration and MCP framework behavior.
- [x] 2.3 Assess response fields and stored data separately; record `comp` as canonical across both, with `composition` retained only as a compatibility alias during migration and rollback implications documented in the matrix.
- [x] 2.4 Assess which config, manifest, policy, documentation, UI, and agent-facing names should change and which internal names can remain; document evidence and migration cost in the matrix.

## 3. Deliver recommendation

- [x] 3.1 Complete `compatibility-matrix.md` with current name, proposed canonical name, alias or migration behavior, affected consumers, breakage risk, evidence, and recommendation for every surface.
- [x] 3.2 Add a staged implementation proposal with rollout order, compatibility period, conflict behavior, rollback approach, and follow-up spec/test/doc work under the same TRN-325 ticket; verify it addresses every high-risk row in the matrix.
- [x] 3.3 Review the matrix and recommendation against TRN-325 and this design; record any decisions needed for implementation and keep the same Plane ticket/OpenSpec change open for the implementation phase.

## 4. Implementation (after delta specs)

- [ ] 4.1 Implement canonical `comp` launch input with the `composition` alias, equal-value acceptance, conflicting-value rejection, and the existing default; verify the generated MCP schema and launch behavior.
- [ ] 4.2 Register `transport://comps` and retain `transport://compositions` as an identical-content alias; verify both are discoverable and readable.
- [ ] 4.3 Rename registry loading to canonical `comps`, accept legacy `compositions`, reject conflicts, and update the authored registry; verify legacy, canonical, matching, and conflicting configurations.
- [ ] 4.4 Make `Crew.comp` canonical; read legacy persisted `composition`, write both same-value fields during the rollback window, and warn when both disagree; verify legacy record loading and serialization.
- [ ] 4.5 Emit canonical `comp` plus equal `composition` aliases in MCP and REST crew payloads; update Radar to read `comp` first and fall back to legacy responses; verify both payload contracts and UI filtering/display.
- [ ] 4.6 Rename internal Python symbols and user-facing errors/descriptions to comp terminology, leaving old terms only in explicit compatibility code; verify no unintended old-name references remain in runtime code.
- [ ] 4.7 Update OpenSpec main specs, tests, README/docs, and installer examples. Coordinate updates to `ghostship-command` and `ghostship-capability` in the sibling executor repo; classify remaining old-term references as aliases or historical text.
- [ ] 4.8 Run focused compatibility tests and the relevant transport suite, validate the OpenSpec change, review rollback behavior, and keep TRN-325 open until all implementation tasks are complete.

## Next action

Run `/openspec-continue-change trn-325-comp-comps-terminology` to create the missing behavior delta specs. Refine implementation tasks against those specs before using `/forge`; do not implement code until the specs are present and validated.
