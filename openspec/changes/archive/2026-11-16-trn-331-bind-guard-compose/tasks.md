# Tasks

## 1. Pass the guard through installation

- [x] 1.1 Add `GA_REQUIRE_SECRET_ON_EXTERNAL_BIND` to `ComposeConfig`, environment resolution, and generated `ga-transport` environment using the existing YAML mapping/default. Verify true and false values in `tests/unit/test_compose.py` and `tests/unit/test_yaml_config.py`.
- [x] 1.2 Add startup tests for specific non-loopback, wildcard, and loopback binds with the secret present/absent and the guard enabled/disabled. Verify actual behavior in `tests/unit/test_server.py` without invoking Podman.

## 2. Correct operator-facing bind documentation

- [x] 2.1 Update `docs/configuration.md` to describe the transport-secret guard and its specific-address/warn-only conditions; correct `README.md` to say the portal defaults to loopback. Verify both documents match the `HOST` and guard requirements in the spec.
- [x] 2.2 Add or update documentation assertions in the relevant installer/config tests, then run `tests/unit/test_compose.py`, `tests/unit/test_yaml_config.py`, and `tests/unit/test_server.py` to verify the documented defaults and generated values remain aligned.
