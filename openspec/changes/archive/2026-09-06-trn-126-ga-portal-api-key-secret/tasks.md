## 1. compose.yml — ga-portal secrets mount

- [x] 1.1 In the `ga-portal` service block of the `compose.yml` heredoc, add `ga-api-key` to the `secrets:` list so it is mounted at `/run/secrets/ga-api-key` inside the container (conditionally, inside the `if [[ -n "${GA_API_KEY:-}" ]]` inline check that already gates whether the line is emitted)
- [x] 1.2 Verify the top-level `secrets:` block already emits `ga-api-key: external: true` when `GA_API_KEY` is set (it does — confirm no duplicate entry is introduced)

## 2. compose.yml — remove GA_API_KEY env var from ga-portal

- [x] 2.1 Remove the `GA_API_KEY: "${GA_API_KEY:-}"` line from the `ga-portal` service `environment:` block in the `compose.yml` heredoc

## 3. initial-config.json — replace env placeholder with secret-file placeholder

- [x] 3.1 In the `_AUTH_ROUTES` heredoc for the `if [[ -n "${GA_API_KEY:-}" ]]` branch, replace `{env.GA_API_KEY}` with `{file./run/secrets/ga-api-key}` in the `/mcp*` route Bearer match expression
- [x] 3.2 Replace `{env.GA_API_KEY}` with `{file./run/secrets/ga-api-key}` in the `/files/*` route Bearer match expression in the same branch

## 4. Verification

- [x] 4.1 Re-read the modified `scripts/install.sh` heredoc sections and confirm: (a) `ga-portal` secrets list includes `ga-api-key` when key is set, (b) `GA_API_KEY` env var is absent from `ga-portal` environment block, (c) both Bearer match expressions use `{file./run/secrets/ga-api-key}`
- [x] 4.2 Run `bash -n scripts/install.sh` to confirm no bash syntax errors introduced
