# Tasks

## 1. Reconcile the network contract

- [x] 1.1 Update network-split, crew-lifecycle, and installation spec requirements to reflect generated Compose memberships; verify each service assignment against bin/lib/compose.py and confirm ga-radar already matches the intended topology.
- [x] 1.2 Correct stale steady-state ga-net descriptions while preserving valid migration steps; verify remaining ga-net mentions against migration code.
- [x] 1.3 Update configuration and architecture docs with the same network table; verify all service memberships agree across specs and docs.
- [x] 1.4 Include all backend-specific login-container prefixes in the network spec and both docs; verify each login payload assigns `ga-starboard`.
- [x] 1.5 Reconcile the dashboard-proxy WebSocket-Origin requirement with runtime behavior and remove the unsupported hostname-Origin/config.local.json claim.
- [x] 1.6 Specify install-time empty ga-net cleanup and uninstall-time removal behavior in the installation delta, verifying it against the installer and uninstaller.

## 2. Validate consistency

- [x] 2.1 Run OpenSpec validation for affected changes/specs and review every result; verify no newly introduced contradiction or placeholder remains.
