# Crew member enrollment

Every agent deployed into a crew at launch time is enrolled as a named KiroCrew
crew member before the crew is declared ready.

## Enrollment

- At crew launch, after the gateway is ready and agent files are deployed, the
  transport enrolls each deployed agent by calling the gateway's member thread
  endpoint for that agent's slug.
- Enrollment is idempotent — re-enrolling an already-enrolled agent is a no-op.
- Enrollment failures for individual agents are non-fatal: the crew still
  launches; unrolled agents operate without attestation.
- The set of enrolled agent slugs is stored in the crew registry and consulted
  at dispatch time.
- On crew restart or recovery, enrollment is re-run to ensure bindings survive
  gateway restarts.

## Attestation guarantee

An agent dispatched into its enrolled member DM slot receives an attested
session identity. Attested sessions can spawn other agents via the gateway's
spawn API using their session key as proof of identity.

An agent dispatched into a non-member slot (e.g. a generic chat slot) does not
receive an attested session and cannot make attested downstream spawns.

## Composition-awareness

Enrollment covers all agents present in the composition's manifest, not a
hardcoded list. Custom compositions with additional or different agents are
enrolled automatically without transport code changes.
