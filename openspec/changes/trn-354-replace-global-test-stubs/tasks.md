## 1. Implementation and verification

- [ ] 1.1 Identify module substitutions in conftest and individual test files. Migrate HTTP consumers to real request, response and exception objects and fake transports.
- [ ] 1.2 Replace ASGI, MCP and remaining dependency substitutions with installed libraries and local fixtures. Isolate import-time and per-test writes to registry, credential, and signing-secret paths. Verify accidental HTTP and Podman calls fail in offline tests.
- [ ] 1.3 Run the full unit suite and offline Python integrations in the same pytest process in both collection orders, then independently. Include gateway-client, on-demand recovery, and profile-launch tests. Preserve shell integration, real Podman, and live E2E entry points.
