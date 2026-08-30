## Context

`_finish_crew_setup` in `server.py` injects various env vars into the crew container at creation time. The current set includes `KIROCREW_HOME`, `KIROCREW_PORT`, `KIROCREW_CORS_ORIGINS`, and auth-related vars. Git identity env vars (`GIT_AUTHOR_NAME` etc.) are honoured by git and kiro-cli's commit paths if present in the container environment.

## Goals / Non-Goals

**Goals:** Let operators set a single identity applied to all crew commits, without editing agent JSONs. Backward-compatible — unset means current behaviour unchanged.

**Non-Goals:** Per-agent identity overrides. Signing commits. Changing the persona name that appears in commit messages.

## Decisions

### Operator-level, not per-agent

**Decision:** A single `GA_GIT_AUTHOR_NAME` / `GA_GIT_AUTHOR_EMAIL` pair applies to all agents in all crews. The persona name can still appear in commit messages or `Co-Authored-By` trailers if the agent includes it, but the `author` field is the human operator.

Per-agent vars (e.g. `GA_GIT_GHOST_AUTHOR_NAME`) were considered but rejected — the common case is "all crew commits look like they came from me", not differentiated per persona.

### Inject all four git vars

**Decision:** When configured, inject all four: `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME`, `GIT_COMMITTER_EMAIL`. Author and committer should match for crew work — splitting them creates confusion.

### Dependency on TRN-75

If TRN-75 (Config dataclass) ships first, `GA_GIT_AUTHOR_NAME` and `GA_GIT_AUTHOR_EMAIL` are added to `Config`. If not, they are read via `os.environ.get()` in `_finish_crew_setup` directly — same pattern as existing vars. Either order works.

### Skill update

Add a short section to `ghostship-command/SKILL.md` covering rewriting authorship after cherry-pick for operators who don't configure identity upfront. This is a one-paragraph addition, not a structural change to the skill.

## Risks / Trade-offs

- If `GA_GIT_AUTHOR_NAME` is set, ALL crew commits carry the operator's name regardless of which agent made them. Operators who want per-persona differentiation must leave these vars unset. Documented in `ghostship.conf.example`.
- No validation that the configured email is well-formed — git accepts arbitrary strings. Not worth adding validation for a cosmetic feature.

## Migration Plan

No migration. Unset → no change in behaviour. Set → new behaviour applied at next `launch`.
