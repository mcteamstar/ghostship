## 1. Retroactive documentation

- [x] 1.1 Confirm `203c9f5` already applies `_sanitise_query_string` to `SecurityHeadersMiddleware`'s redirect target (`transport/server.py:~1056`) — verified by reading the current code.
- [x] 1.2 Write the `security-headers` capability spec covering the redirect + sanitisation behavior.
- [x] 1.3 Sync the new capability into `openspec/specs/` and archive this change.
