# Spec delta — secret-delivery-hardening

## Changed requirements

### inject_policy.py uses stdin for HMAC key delivery

`inject_policy.py` SHALL read the HMAC policy signing key from `sys.stdin`
(via `sys.stdin.read().strip()`), not from `sys.argv`. The caller in
`lifecycle.py` SHALL deliver the key via the `input` parameter of
`container_exec_stdin`, closing the write end after the key is written. The key
SHALL NOT appear in any element of `argv` of the `inject_policy.py` process.
