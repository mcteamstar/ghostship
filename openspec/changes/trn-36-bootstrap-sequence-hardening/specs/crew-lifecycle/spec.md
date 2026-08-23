## MODIFIED Requirements

### Requirement: Crew setup completion is all-or-nothing

The system SHALL only mark a crew "running" after all required setup steps have
succeeded, and SHALL clean up the crew if any required step fails. Auth injection
SHALL be verified by exit code, not by pattern-matching the output string.

The setup steps SHALL execute in dependency order:

1. Wait for gateway (pre-restart)
2. Inject kiro-cli auth (`_inject_auth`)
3. Generate and inject admiral signing secret — alongside auth, before restart,
   so the secret is in place before Raven can ever run
4. Patch crew config (`_patch_crew_config`)
5. Container restart (auth + config take effect)
6. Wait for gateway (post-restart)
7. Copy agents, skills, steering
8. Seed OpenSpec store
9. Inject security policy (depends only on admiral secret, not on the gateway)
10. Wait for KiroCrew to seed built-in agent files (gateway-dependent)
11. Patch model overrides
12. Mint session cookie
13. Read version label, write registry entry

The admiral signing secret write SHALL use `os.fsync` before closing the file
descriptor to ensure the write is durable before any process inside the container
can read the file.

#### Scenario: Successful setup

- **WHEN** all setup steps succeed
- **THEN** the crew is marked "running" and the admiral secret is present in the
  container before the post-restart gateway ever becomes reachable

#### Scenario: Admiral secret present before post-restart gateway

- **WHEN** the transport has completed auth injection and the pre-restart gateway
  wait, and then restarts the container
- **THEN** the admiral secret file exists at
  `/home/kirocrew/.kiro/crew/.admiral_secret` before any post-restart gateway
  call is made

#### Scenario: Cookie mint fails

- **WHEN** every step up to and including cookie minting succeeds except
  `_mint_cookie`
- **THEN** the crew is cleaned up and `launch` returns an error
