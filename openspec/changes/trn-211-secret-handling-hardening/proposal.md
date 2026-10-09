# Proposal

Source: independent review of `release/0.6.0` at `ee0b3b8` (2026-10-09), run on the Claude backend. Reviewers: **S** security, **Q** quality, **T** test coverage, **D** docs. "Reproduced" means the reviewer or a live check ran code to confirm it; everything else is from reading the code and needs confirming during assessment. Target: a release after 0.6.0.

Full reviewer reports: crew `ghostship-indy-060` tasks `169e9101b28e91e4` (security), `d615d73e3b7c9e37` (quality), `408dea89af5f6789` (test coverage), `45df3b672a262c4c` (docs) — retrieve with `pickup(task_id, crew_id)` while the crew exists. Line numbers refer to `ee0b3b8` and may drift. Next step for whoever picks this up: work through **Assess first**, then write specs, design and tasks with `openspec instructions <artifact> --change <name>`.

## Why

Secrets reach places with weaker protection than the rest of the system: plaintext in a world-readable compose file, dropped entirely, or exposed to the agent they constrain.

## Findings

| Severity | Finding | Where | Who | Status |
|---|---|---|---|---|
| Medium | `GA_CREW_ANTHROPIC_API_KEY` and `GA_CREW_OPENAI_API_KEY` are written as plain values into `compose.yml`. The file is now mode 600, but the keys should be Podman secrets like `GA_API_KEY`. | `install.sh` compose env | Q | Mode fixed; secrets open |
| High | `KIRO_API_KEY` is read by the transport but never passed by `install.sh`, so the documented headless kiro path silently falls back to device login. | `config.py:326`; `install.sh` compose env | D | Read only |
| Medium | Policy HMAC key is readable by the agent it governs (same UID). Documented as accepted residual risk; confirm whether the policy is meant to constrain the agent. | `lifecycle.py:1852`; `inject_policy.py`; `auth.md:370` | S | Read only |
| Medium | Transport holds the rootless Podman socket with `label=disable`; transport compromise equals control of every container. | `install.sh:725`, `:738` | S | Design risk |
| Low | Fixed `/tmp` staging paths for credential chunks inside the crew follow pre-existing symlinks. | `lifecycle.py:2180`, `:2877` | S | Read only |
| Low | The gateway token is sent as a query parameter when minting the session cookie, so the gateway's access log records it. | `lifecycle.py:1171` | S | Read only |
| Low | `--api-key` on the command line is visible in the process list and shell history. | `install.sh:166` | S | Read only |

## Assess first

- Decide whether model API keys and `KIRO_API_KEY` become Podman secrets (preferred) or a `umask 077` compose file.
- Confirm what the gateway enforces with the signed policy before deciding on the HMAC key.

## What Changes

- Model API keys and `KIRO_API_KEY` delivered as Podman secrets, like `ga-api-key`.
- `mktemp` staging in a 0700 directory; send the gateway token in a header or body; offer a config or file option for the API key instead of a flag.
- Scope the Podman socket (allowlisting proxy) if feasible.

## Capabilities

### New Capabilities

- None expected.

### Modified Capabilities

- `secret-delivery-hardening`: model and kiro keys via secrets.
- `installation`: compose file never contains secret values.

## Impact

`scripts/install.sh`, `transport/config.py` (secret loading), `transport/lifecycle.py`. Operators with keys in `ghostship.conf` keep working; the delivery mechanism changes.
