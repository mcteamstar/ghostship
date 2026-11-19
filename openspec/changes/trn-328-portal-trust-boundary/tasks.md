# Tasks

## 1. Establish the socket boundary

- [ ] 1.1 Verify Caddy and Transport runtime UID/GID in the pinned images and confirm Caddy supports the Unix admin socket path; record shared-group ownership and permissions.
- [ ] 1.2 Configure the shared socket volume and restrictive permissions; verify only ga-portal and ga-transport mount it and no TCP admin listener or host mapping remains.
- [ ] 1.3 Route Transport admin requests through the socket and update registration, deregistration, and reconciliation tests to use it.

## 2. Enforce dashboard authorization

- [ ] 2.1 Check the original dashboard session at the Transport HTTP UI proxy when API-key auth is enabled; verify direct internal calls without a session receive 401 before the crew gateway is contacted.
- [ ] 2.2 Preserve the open-install path and verify a valid dashboard session can proxy requests on keyed and open installations.

## 3. Verify the combined trust boundary

- [ ] 3.1 Add regression coverage showing Radar cannot access the Caddy socket or proxy a dashboard request using only the transport secret; run focused Caddy/dashboard tests.
- [ ] 3.2 Update architecture and portal docs to describe the internal-only admin socket and Transport session gate; verify claims match Compose and middleware behavior.
