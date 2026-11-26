# Tasks

## 1. Interactive device-code handoff

- [x] 1.1 Add terminal input monitoring to the device-code polling wait, show the Enter hint, and open the login URL on Enter; verify unit tests cover opening, repeated Enter, and continued polling.
- [x] 1.2 Handle browser opener failure and non-interactive input while preserving authorization-code behavior; verify unit tests cover failure reporting, non-TTY polling, and the unchanged authorization-code path.
