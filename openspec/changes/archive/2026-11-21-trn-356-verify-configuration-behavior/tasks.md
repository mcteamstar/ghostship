## 1. Implementation and verification

- [x] 1.1 Replace signed URL source checks with supply and evac entry-point tests for explicit public URL and portal-host fallback, including a non-default port.
- [x] 1.2 Replace CORS source checks with a launch-path test that captures KIROCREW_CORS_ORIGINS. Exercise explicit public URL precedence and portal-authority fallback, including an external base with a path.
- [x] 1.3 Test startup with an internal wildcard bind and a loopback portal, a non-loopback portal without a key, explicit opt-out, and a configured key. Assert process rejection or successful startup progression and the opt-out warning. Run focused config, file, launch, and server tests.
