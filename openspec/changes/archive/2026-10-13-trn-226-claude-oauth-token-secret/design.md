# Design

## Context

Claude-backend crews currently authenticate in one of two ways (see proposal.md, Why):

- **API key.** `GA_CREW_ANTHROPIC_API_KEY` goes to the Podman secret `ga-crew-anthropic-api-key` (`install.sh:717`). `server.py` reads `/run/secrets/…` at startup and registers it for redaction (`server.py:476-490`), then sets `ANTHROPIC_API_KEY` in `container_env` at create time (`server.py:2785`).
- **OAuth.** `ga-claude-auth` (a tar of `~/.claude/`) is copied into the crew by `_inject_claude_auth` during `_finish_crew_setup`, but only when no API key is set (`lifecycle.py:2146`).

The launch gate (`server.py:2628`) accepts either one. `KIRO_API_KEY` and `GA_CREW_OPENAI_API_KEY` follow the same config, secret, env pattern. The broken route lives at `server.py:2055` (handler) and `lifecycle.py:3334` (`_initiate_claude_setup_token`), with tests in `tests/unit/test_trn226_claude_setup_token.py`.

## Goals / Non-Goals

**Goals:**
- The setup-token travels the same path as the existing model keys, with no new mechanism.
- A Claude-backend crew receives exactly one credential.

**Non-Goals:**
- Detecting token expiry or warning ahead of it.
- Changing the interactive OAuth flow or the OAuth refresh-staleness behaviour for operators who stay on it.
- Generating the token for the operator.

## Decisions

**1. Static config secret, not a login flow.** The operator runs `claude setup-token` on their own machine and puts the result in `ghostship.conf`. *Alternative:* fix the endpoint by driving `claude setup-token` over a PTY, returning its URL, accepting the pasted code and scraping the printed token. That duplicates the OAuth state machine (pending state, expiry sweep, orphan cleanup) for a credential that is only made about once a year, and parsing the token out of terminal output is fragile. The config path already exists, has rotation by reinstall, and is covered by secret-delivery tests.

**2. Inject as `CLAUDE_CODE_OAUTH_TOKEN`.** This is the environment variable Claude Code reads for setup-token credentials. *Alternative:* write the token into `~/.claude/.credentials.json`. That format is undocumented and is the file the refresh cycle rewrites, which is the source of the staleness problem.

**3. One credential per crew, with precedence API key, then token, then `ga-claude-auth`.** Resolve the precedence in the transport so the crew never holds two Claude credentials. That way it doesn't matter how Claude Code ranks them internally (which may change between versions), and a stale `~/.claude/` cannot shadow the token. Concretely, the `container_env` block gains an `elif` for the token, and the `_finish_crew_setup` guard becomes `not API_KEY and not OAUTH_TOKEN and _claude_auth_exists()`.

**4. Naming: use the standard variable name.** The config setting is `CLAUDE_CODE_OAUTH_TOKEN`, the name Claude Code itself reads, so `ghostship.conf` and the crew environment use the same name. *Alternative:* a `GA_CREW_*` prefix like the existing model keys. The prefix adds nothing, because the name already says which tool it belongs to, the same as `KIRO_API_KEY`. The secret follows the `KIRO_API_KEY` to `ga-kiro-api-key` convention: `ga-claude-code-oauth-token`. Transport names are `_CLAUDE_CODE_OAUTH_TOKEN` (server), `CLAUDE_CODE_OAUTH_TOKEN` (lifecycle) and `Config.claude_code_oauth_token`. The same reasoning applies to the existing model keys; see decision 7.

**5a. Both modules resolve credentials from the secret file.** Implementation found that `lifecycle.py` read `KIRO_API_KEY` and the Anthropic and OpenAI keys from `cfg`. Those values are always `""` in production, because the keys exist only as Podman secrets and only `server.py` read the secret files. As a result, lifecycle's OAuth-injection guards (`not GA_CREW_ANTHROPIC_API_KEY and _claude_auth_exists()`, and the kiro and codex equivalents) ignored a configured API key, and crews got both credentials. Both modules now call `security.get_secret(<secret>, env_var=<VAR>)` for all four credentials. That helper reads the secret file first, falls back to the env var for dev and test, and registers the value for redaction. The old `server._read_podman_secret` is removed. The inert-setting warning likewise checks the resolved values, not `cfg`. *Alternative:* fix only the token. Rejected by the Admiral: the existing keys had the same defect.

**6. Ignore the operator's shell environment.** A standard name means the operator may already have `CLAUDE_CODE_OAUTH_TOKEN` exported for their own Claude Code use. `install.sh` resets it to `""` in its defaults block before sourcing `ghostship.conf`, as it already does for `KIRO_API_KEY`. Only a value written in the config file reaches crews.

**5. Remove the route outright (404).** *Alternative:* keep it returning 410 with a migration hint. It never succeeded, so there are no working callers to guide. A smaller surface is better, and the CHANGELOG and `docs/auth.md` carry the migration.

**7. Rename the model backend settings, with aliases in install.sh only.** `GA_CREW_ANTHROPIC_*` and `GA_CREW_OPENAI_*` become `ANTHROPIC_*` and `OPENAI_*`. The old names are mapped in `install.sh`, after the config file and flags are processed, because that is the only place operators set them. The transport only ever receives what `install.sh` writes (the secrets plus the base URLs in compose `environment:`), so it reads the new names only and needs no alias. Secret names (`ga-crew-*-api-key`) are unchanged, so an existing install keeps working after the upgrade without touching Podman. *Alternative:* also alias in `Config.from_env`. That would only help someone running the transport outside `install.sh`, and it would make the transport's secret fallback and `Config` disagree on names.

## Risks / Trade-offs

- **The token expires (believed to be about a year; verify against current Claude Code docs) and crews fail with an auth error and no warning beforehand.** → The docs state the lifetime and the rotation steps (new token, update conf, reinstall, relaunch crews).
- **Env var changes only reach crews created after a reinstall, because env is fixed at container create.** → The docs say to nuke and relaunch Claude crews after rotating. This matches how API-key rotation already behaves.
- **The token is visible in the crew container's environment to processes in that crew.** → Same exposure as `ANTHROPIC_API_KEY` today. It stays out of compose and is redacted from transport logs.
- **Operators who set both the token and keep `ga-claude-auth` may expect OAuth to be used.** → Precedence is documented. A `POST /logout/claude` is optional cleanup.

## Migration Plan

1. Run `claude setup-token` locally and copy the token.
2. Add `CLAUDE_CODE_OAUTH_TOKEN="…"` to `ghostship.conf` and run `ghostship install`.
3. Nuke and relaunch existing Claude-backend crews (evac first).
4. Optionally run `POST /logout/claude` to delete the now-unused `ga-claude-auth`.

Rollback: remove the setting and reinstall. Crews fall back to `ga-claude-auth` if it is still present, otherwise launch prompts for OAuth login.

## Open Questions

- The exact setup-token lifetime, needed for the docs wording only.
