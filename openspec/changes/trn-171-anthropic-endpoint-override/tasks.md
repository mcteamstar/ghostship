## 1. Config

- [ ] 1.1 Add `ga_crew_anthropic_base_url: str = ""` to `Config` dataclass in `transport/config.py`
- [ ] 1.2 Add `GA_CREW_ANTHROPIC_BASE_URL` binding in `Config.from_env()` (`os.environ.get("GA_CREW_ANTHROPIC_BASE_URL", "").strip()`)
- [ ] 1.3 Add `GA_CREW_ANTHROPIC_BASE_URL` to the compose env block in `scripts/install.sh` (`GA_CREW_ANTHROPIC_BASE_URL: "${GA_CREW_ANTHROPIC_BASE_URL:-}"`)

## 2. Transport

- [ ] 2.1 In `server.py` `launch()`, in the `container_env` block where `ANTHROPIC_API_KEY` is conditionally injected: add injection of `ANTHROPIC_BASE_URL` from `_GA_CREW_ANTHROPIC_BASE_URL` when `GA_CREW_ACP_BACKEND == "claude"` and the value is non-empty
- [ ] 2.2 In `lifecycle.py` `_finish_crew_setup()`, update the `api.anthropic.com` WARNING log to use the effective endpoint: `_GA_CREW_ANTHROPIC_BASE_URL` if set, otherwise `api.anthropic.com`; expose `GA_CREW_ANTHROPIC_BASE_URL` as a module-level from config (same pattern as `GA_CREW_ACP_BACKEND`)

## 3. Docs and Config

- [ ] 3.1 Add `GA_CREW_ANTHROPIC_BASE_URL` to `docs/configuration.md` in the Claude backend section — optional, default unset, note it has no effect on kiro-backend crews
- [ ] 3.2 Add commented-out `# GA_CREW_ANTHROPIC_BASE_URL=""` entry to `config/ghostship.conf.example` in the Claude backend section

## 4. Tests

- [ ] 4.1 Unit test: `GA_CREW_ANTHROPIC_BASE_URL` set with Claude backend → `ANTHROPIC_BASE_URL` present in `container_env`
- [ ] 4.2 Unit test: `GA_CREW_ANTHROPIC_BASE_URL` unset with Claude backend → `ANTHROPIC_BASE_URL` absent from `container_env`
- [ ] 4.3 Unit test: `GA_CREW_ANTHROPIC_BASE_URL` set with kiro backend → `ANTHROPIC_BASE_URL` absent from `container_env`
