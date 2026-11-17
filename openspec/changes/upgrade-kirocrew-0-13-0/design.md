# Design

## Context

- One immutable pin, `KC_BASE_IMAGE`, drives three things. It is the admission `FROM` (`crews/_base/admission/Containerfile`), the transport default (`transport/config.py`, `kc_base_image`), and the image used for ephemeral `ga-login-*` containers. Moving it moves crews and the kiro-cli that captures kiro credentials together.
- The kiro-cli DB is pre-seeded at build time (`crews/_base/graduation/seed_kiro_db.py`) so that auth injection is a plain insert. The seed is verified against v0.12.2: Kiro CLI 2.27.1, 11 migration rows, versions 0 to 10. The Containerfile warns that a pin bump without re-verification is a silent auth-injection regression.
- Ghostship's spawn bodies today: `dispatch` sends `{task, agent, keep: true}` plus `parent_session` for enrolled agents (`transport/tools.py`, `transport/lifecycle.py` `_dispatch_batch`). Captain sends `parent_session: "dashboard:member-raven"` (`transport/captain_engine.py`). None names a backend.
- In KiroCrew `0.13.0-rc.3`, `POST /api/spawn` uses the body's `backend`. When it is absent, the backend comes from `_inherited_backend_name`, which returns a harness only when the parent session was created with a pick (`session_create(backend=...)`). Otherwise the run starts on the gateway default (`src/kiro_crew/dashboard/messaging_api/spawn.py:224-240`, `:536-539`). Request spellings come from `POLICY_ID_BY_BACKEND` (`src/kiro_crew/agent_sdk/backends.py:742`). The default backend is spelled `kiro`, and `kas`, `claude` and `codex` are separate ids.
- Ghostship kiro crews get no `agent.acp_backend` override, so they run on KiroCrew's default backend. Claude and Codex crews get `agent.acp_backend` set to `claude` or `codex` (`transport/lifecycle.py`, crew config patch).
- Already on `release/0.13.0`: the Identity Center login waits for `api.codewhisperer.profile` before storing a credential (`54c7babb`), and the transport records `kiro_signin` (`efc5dfe5`). Both are exercised by this change's smoke checks.

## Goals / Non-Goals

**Goals:**

- One mapping from a crew's recorded `acp_backend` to the gateway's request spelling, used by every transport spawn site.
- Seed and image verification on a host with Podman, by querying the image directly, not only by layer inspection.
- A release gate that makes it impossible to ship Ghostship 0.13.0 on a release-candidate pin.

**Non-Goals:**

- Changing the in-crew `ghostship-spawn` helper or any agent-facing spawn surface.
- Dashboard visibility of dispatched work, and adopting Bot-native work dispatch.
- Migrating existing crews automatically. They keep their image until an operator recreates them.

## Decisions

### D1. Validate on rc.3 now, gate release on the final digest

Pin `0.13.0-rc.3` (`sha256:189c5716...c509e9`, amd64 and arm64 verified from the GHCR index) and do the full verification now. A tasks.md gate requires re-pinning to the final `0.13.0` digest and repeating the image, seed and smoke checks before release.

- Alternative: wait for the final tag. Rejected because it delays finding schema or integration breaks until release week.
- Alternative: ship on rc.3. Rejected because release candidates can change before final, and a pin that never moves is unreviewed drift.

### D2. Map the recorded backend in one helper, never to `kas`

Add a single transport helper that turns a crew's registry `acp_backend` into the gateway spelling: `kiro` to `"kiro"`, `claude` to `"claude"`, `codex` to `"codex"`, and missing to `"kiro"`. All three spawn sites call it.

`kiro` maps to the policy id of KiroCrew's default backend, which is what Ghostship kiro crews run today, so naming it changes nothing on the normal path. It only removes the inheritance path.

- Alternative: omit the field and rely on the gateway default. Rejected because v0.13 inheritance makes the runtime depend on session state Ghostship does not control.
- Alternative: read the backend from the crew's gateway config at spawn time. Rejected because it adds a gateway call per dispatch, and the registry is already the source of truth for restarts.
- Alternative: map `kiro` to `"kas"`. Rejected because KAS is a distinct gateway backend id. Naming it could move kiro crews onto a different harness. The smoke check confirms that `"kiro"` runs the same harness as an unnamed spawn.

### D3. Surface a backend refusal, do not retry without it

If the gateway refuses the named backend (`_requested_backend` returns a 4xx listing startable backends), `dispatch` returns that error, and Captain records the failed check-in as it does any spawn error. Retrying without the field would quietly reinstate the inheritance this change removes.

### D4. Verify the seed by querying the image

Podman is available on this build host, unlike the TRN-324 Carrier run, which could only inspect published layers. Verification runs a throwaway container from the pulled base image. It initialises the kiro-cli runtime, reads `migrations` (count and max version) and the `sqlite_master` definitions, and compares them with `seed_kiro_db.py`. It is not a crew container, so the transport-only rule for crews is not involved. Layer inspection is the fallback.

### D5. Login is verified with the new kiro-cli, not assumed

The login container moves to the new image's kiro-cli. KiroCrew 0.13's Identity Center profile fixes are in the gateway's sign-in path, not in `kiro-cli login`. So Ghostship's profile wait (`54c7babb`) stays and is re-verified: a fresh Identity Center login on the new image must store a credential whose `state` holds `api.codewhisperer.profile`.

## Risks / Trade-offs

- [The rc.3 schema or behaviour changes in the final release] → D1's gate repeats every check against the final digest. The seed requirement covers every pin change.
- [`"kiro"` and an unnamed spawn behave differently on some gateway configuration] → The smoke check compares a named and an unnamed spawn on a fresh kiro crew before the helper ships.
- [v0.13 Bot changes affect Captain's `member-raven` parent (the conductor-only Bot chat, ledger defaults, and `kirocrew-mate-conductor` refusing `spawn_run` from a Bot chat)] → The refusal applies to tool calls made inside the Bot chat, not to an external `POST /api/spawn` that names the slot as parent (inferred from the discovery). A Captain check-in on a fresh crew is part of the smoke checks.
- [Rebuilding the transport and login images interrupts in-flight logins and Captain check-ins] → Rebuild between operations. Captain resumes on its next interval.
- [Existing crews stay on v0.12.2 until recreated] → Document it in the changelog. Recreation is the operator's call (evac, nuke, launch).

## Migration Plan

1. Land the pin, seed, backend helper and docs on `release/0.13.0`.
2. Rebuild with `ghostship install` or `ghostship upgrade`. This recreates `ga-transport` and the images, and running crews are untouched.
3. Run a fresh kiro Identity Center login and launch fresh kiro and claude crews to verify.
4. Operators adopt the new image per crew by recreating it.
5. Rollback: restore the previous `KC_BASE_IMAGE` digest and seed annotation together, rebuild, and verify authentication on a fresh crew. The backend field is harmless on v0.12.2 (the body field exists there), so it does not need reverting.

## Open Questions

- When the final `0.13.0` tag is published. This affects only when the D1 gate can be closed, not the approach.
