# Design

## Context

Crew setup resolves a backend and profile, but Codex and Claude OAuth injection helpers read shared legacy archive paths. OAuth completion also writes the shared archive and catches profile-store errors. The registry already stores the resolved profile, while the successful launch result omits it.

## Goals / Non-Goals

**Goals:** Preserve identity across credential lifecycle operations and accurately report the selected profile; maintain existing default-profile installations.

**Non-Goals:** Change authentication providers, expose credential contents in APIs, or redesign the profile naming scheme.

## Decisions

1. Resolve the exact backend/profile payload once at the trust boundary and pass it explicitly to injection, rather than allowing helpers to select a shared file. Audit all launch, post-login propagation, restart, refresh and recovery paths for Kiro, Claude and Codex; make missing or malformed selected OAuth payloads fail clearly rather than using another profile. Preserve environment-based API-key and setup-token flows.
2. Treat the profile store as authoritative for profile-aware OAuth. Migrate or read legacy archives only for the implicit default when no newer default profile exists; never allow named flows to overwrite or consume the shared default. Keep migration idempotent and do not delete an operator's sole credential before a successful durable write. Audit existing flow completion, logout and concurrency locks to avoid stale writes or cross-profile propagation.
3. Commit selected-profile persistence before reporting success. If persistence fails, leave the pending flow recoverable and avoid cleanup or success reporting. Test atomicity for partial writes and concurrent cancellation; avoid credential values in logs, exceptions, results and tests.
4. Add `acp_profile` to all successful launch paths from the resolved profile, with existing fields and error shapes preserved. Compare response with stored registry state.

## Risks / Trade-offs

- Legacy installs may have only shared credentials → test forward migration with synthetic archives and existing profile-store versions.
- Concurrent login, logout and crew startup can interleave → test per-profile isolation and flow cancellation with fault injection.
- Authentication data is sensitive → use fake payloads, private temporary files and redact logs; never snapshot real credentials.

## Migration Plan

On first default-profile use migrate safely or use the documented default-only compatibility path. Verify existing default and named credentials remain selectable after upgrade. Upgrades are forward-only; compatibility with rolling back to older versions is not required.
