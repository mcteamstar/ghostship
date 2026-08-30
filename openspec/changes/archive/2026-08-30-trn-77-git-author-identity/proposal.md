## Why

Commits made by agents inside crew containers use generic identities (`Ghost <ghost@localhost>`, `Banshee <banshee@localhost>`, etc.). When an operator evacs work and cherry-picks it into their local repo, these generic author labels end up in the project history. There is no way to configure this without editing agent definitions.

## What Changes

- Add two optional env vars to `ghostship.conf`: `GA_GIT_AUTHOR_NAME` and `GA_GIT_AUTHOR_EMAIL`
- Inject them as `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME`, `GIT_COMMITTER_EMAIL` into the crew container at creation time in `_finish_crew_setup`
- When unset, current per-persona identity is preserved — no breaking change
- Add a note to the `ghostship-command` skill about rewriting authorship after cherry-pick for operators who don't configure identity upfront
- Update `config/ghostship.conf.example` and `docs/configuration.md` to document the new vars

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `config-file`: two new optional operator-level variables (`GA_GIT_AUTHOR_NAME`, `GA_GIT_AUTHOR_EMAIL`) control the git author/committer identity injected into crew containers

## Impact

- `transport/server.py` — `_finish_crew_setup` injects git identity env vars when configured
- `config/ghostship.conf.example` — two new commented-out entries
- `docs/configuration.md` — new rows in the env var reference table
- `.claude-plugin/skills/ghostship-command/SKILL.md` — note on rewriting authorship after cherry-pick
- Natural companion to TRN-75 (Config dataclass) — these vars should be added to `Config` as part of that change; if TRN-75 ships first, add them there; if not, add them to `server.py` directly
