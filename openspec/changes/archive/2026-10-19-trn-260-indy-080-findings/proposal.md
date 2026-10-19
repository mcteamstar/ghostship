# Proposal

## Why

The indy-080 independent review of ghostship 0.8.0 surfaced four findings that
must be addressed before the release PR is opened. Two are security issues
(one critical, one high), one is a deprecated API usage, and one is a wrong
default value. All four are small, targeted fixes with no architectural impact.

## What Changes

- **C-1 (Critical):** Restore six spec-mandated test modules deleted in TRN-244
  (`a2ff151`) and never recreated: `test_ws_proxy.py`, `test_podman_exec_stdin.py`,
  `test_streaming_transfer.py`, `test_tls.py`, `test_trn237_csp_nonce.py`,
  `test_trn221_no_hardcoded_sel_path.py`. Tests must cover the behaviours their
  names describe.
- **H-1 (High):** `transport/lifecycle.py` passes the HMAC policy signing key as
  a command-line argument to `inject_policy.py`, exposing it via
  `/proc/<pid>/cmdline`. Switch to stdin delivery following the TRN-211 /
  `secret-delivery-hardening` spec pattern.
- **M-4 (Medium):** `transport/files.py` calls `hmac.new()` (3 occurrences),
  which is deprecated since Python 3.4. Replace with `hmac.HMAC()`.
- **L-1 (Low):** `transport/config.py` dataclass default for
  `ga_dashboard_port_range_size` is `1024`; the correct value matching the YAML
  default and documentation is `64`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `secret-delivery-hardening`: H-1 violates the existing "Secrets delivered via
  stdin, not process arguments" requirement. The spec already mandates this; the
  delta confirms `inject_policy.py` is in scope and compliant after this fix.
- `transport-test-coverage`: Six previously spec-mandated test modules are absent.
  The delta restores coverage requirements for ws-proxy, podman-exec-stdin,
  streaming-transfer, TLS, CSP nonce (TRN-237), and no-hardcoded-sel-path (TRN-221).

## Impact

- `transport/lifecycle.py` — switch argv key delivery to stdin for `inject_policy.py`
- `transport/container_scripts/inject_policy.py` — read key from stdin
- `transport/files.py` — 3× `hmac.new()` → `hmac.HMAC()`
- `transport/config.py` — `ga_dashboard_port_range_size` default `1024` → `64`
- `tests/unit/` — add six missing test modules
