## 1. Transport implementation

- [ ] 1.1 Add `GA_GIT_AUTHOR_NAME` and `GA_GIT_AUTHOR_EMAIL` env var reads in `_finish_crew_setup` (or to `Config` if TRN-75 has landed)
- [ ] 1.2 When both vars are set, inject `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME`, `GIT_COMMITTER_EMAIL` into the crew container's environment at creation time

## 2. Config and docs

- [ ] 2.1 Add `GA_GIT_AUTHOR_NAME` and `GA_GIT_AUTHOR_EMAIL` to `config/ghostship.conf.example` as commented-out entries with a description
- [ ] 2.2 Add both vars to the env var reference table in `docs/configuration.md`

## 3. Skill update

- [ ] 3.1 Add a short section to `.claude-plugin/skills/ghostship-command/SKILL.md` covering: how to configure identity upfront via `ghostship.conf`, and how to rewrite authorship after cherry-pick for operators who don't

## 4. Unit tests

- [ ] 4.1 Add unit test: when `GA_GIT_AUTHOR_NAME` and `GA_GIT_AUTHOR_EMAIL` are set, all four git env vars are injected into the container env at creation
- [ ] 4.2 Add unit test: when `GA_GIT_AUTHOR_NAME` is unset, no git identity env vars are injected

## 5. Verification

- [ ] 5.1 Run `bash tests/run.sh --unit` — all tests pass
- [ ] 5.2 Run `bash tests/run.sh --integration` — all tests pass
