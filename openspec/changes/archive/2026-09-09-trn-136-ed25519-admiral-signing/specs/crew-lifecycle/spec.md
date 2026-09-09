## MODIFIED Requirements

### Requirement: Crew setup completion is all-or-nothing

The system SHALL only mark a crew "running" after all required setup steps have
succeeded, and SHALL clean up the crew if any required step fails. Auth injection
SHALL be verified by exit code, not by pattern-matching the output string.

The Admiral Ed25519 keypair is established **before** crew setup begins, as part
of container creation rather than as a setup step: the transport generates the
keypair, persists the private seed host-side, registers the public key as a
Podman secret, and attaches that secret to the `container_create` spec. The
public key is therefore present in the container from the moment it first
starts, and no setup step injects it. See the `crew-auth` capability for the
keypair requirements.

The setup steps SHALL execute in dependency order:

1. Wait for gateway (pre-restart)
2. Inject kiro-cli auth (`_inject_auth`)
3. Generate the `policy_signing_key` — before restart, so it is in place before
   the security policy is injected
4. Patch crew config (`_patch_crew_config`) — including the required `agent`
   field sourced from `GA_CREW_AGENT` (default: `"kiro"`)
5. Container restart (auth + config take effect)
6. Wait for gateway (post-restart)
7. Copy agents, skills, steering
8. Seed OpenSpec store
9. Inject security policy (depends only on `policy_signing_key`, not on the
   gateway and not on the Admiral keypair)
10. Wait for KiroCrew to seed built-in agent files (gateway-dependent)
11. Patch model overrides — write `agents` directory files **before** calling
    any gateway endpoint, because the agents directory is write-protected at
    runtime in KiroCrew 0.5.0
12. Mint session cookie
13. Read version label, write registry entry

The host-side write of the Admiral private seed SHALL use `os.fsync` before
closing the file descriptor, so the seed is durable before any standing order
can be signed against it. Durability is no longer about in-container
readability: the private seed never enters the container.

The `_patch_crew_config` call in step 4 (pre-restart) SHALL write the `agent`
field into `config.local.json` so the gateway picks it up on first start. The
field SHALL be sourced from the `GA_CREW_AGENT` transport environment variable
(default: `"kiro"`).

The `_copy_agents` call (step 7) — and any other setup step that writes agent
JSON files into `KIRO_AGENTS_DIR` — SHALL occur **after** the post-restart
gateway is ready and SHALL NOT be called after the gateway is already serving
requests, because KiroCrew 0.5.0 makes the agents directory write-protected at
runtime.

#### Scenario: Successful setup

- **WHEN** all setup steps succeed
- **THEN** the crew is marked "running", and the Admiral public key has been
  present in the container since it first started

#### Scenario: Admiral secret present before post-restart gateway

- **WHEN** the transport has completed auth injection and the pre-restart gateway
  wait, and then restarts the container
- **THEN** the Admiral key material the crew needs is already in place, because
  the public key was attached to the `container_create` spec as a read-only
  Podman secret and has been readable at `/run/secrets/.admiral_public_key`
  since the container first started. No setup step writes it, and the guarantee
  now holds from container creation rather than from just before the restart

#### Scenario: No setup step writes the Admiral key into the container

- **WHEN** crew setup runs to completion
- **THEN** no `container_exec` call writes Admiral key material, and the private
  seed exists only host-side

#### Scenario: Cookie mint fails

- **WHEN** every step up to and including cookie minting succeeds except
  `_mint_cookie`
- **THEN** the crew is cleaned up and `launch` returns an error

#### Scenario: Auth injection failure is detected
- **WHEN** the auth injection command exits with a non-zero exit code
- **THEN** the system treats the injection as failed, does not proceed with the remaining setup steps, and tears down the partially-created crew

#### Scenario: Auth injection output is not used as a success signal
- **WHEN** the auth injection command exits with a non-zero exit code but its output contains the word "injected"
- **THEN** the system treats the injection as failed, not as successful

#### Scenario: Agent files written before runtime write-protection
- **WHEN** `_copy_agents` is called during crew setup
- **THEN** the agent JSON files are written to `KIRO_AGENTS_DIR` during the
  post-restart gateway startup window, before KiroCrew 0.5.0 makes that
  directory write-protected at runtime
