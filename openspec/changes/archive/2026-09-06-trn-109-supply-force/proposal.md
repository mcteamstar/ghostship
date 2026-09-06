## Why

When `supply` is called with `bundle=True` and the destination path already exists in the crew workspace (e.g., the crew was previously seeded with a repo), `git clone` refuses to clone into a non-empty directory and the delivery fails with a 500 error. Long-lived crews that need to receive an updated repo snapshot have no clean first-party path — operators must dispatch a separate task to `rm -rf <path>` before re-supplying, which is awkward and error-prone.

## What Changes

- `supply()` in `transport/server.py` gains an optional `force: bool = False` parameter. When `force=True` and `bundle=True`, the pre-clone step removes the destination path before cloning, enabling idempotent re-seeding.
- `_transfer_upload()` in `transport/files.py` gains the corresponding `force: bool = False` parameter. When `force=True` and `bundle` mode is active, it runs `rm -rf <destination>` inside the container before the `git clone` call.
- The presigned upload URL's HMAC payload is extended to include the `force` flag, alongside the existing `bundle` and `unpack` flags, so a token signed without `force` cannot be replayed to trigger destructive pre-clone removal.
- `_sign_upload_url()` and `_verify_file_token()` in `transport/files.py` are updated to include `force` in the sorted flags string used for HMAC signing/verification.
- A unit test is added covering the `force=True` re-seed path: `_transfer_upload` removes an existing destination before cloning when `bundle=True, force=True`.

## Capabilities

### New Capabilities

None. The `force` flag is a parameter extension of the existing `supply` tool, not a new capability.

### Modified Capabilities

- `file-transfer`: The "Seed a repository from a bundle" requirement gains a new opt-in variant — a force re-seed that first removes the existing destination. The existing "Reject a bundle delivery into an occupied destination" scenario remains the default (force=False) behaviour. A new scenario is added for `force=True`. The HMAC signing requirement is extended to include the force flag.
- `file-transfer-security`: The operation-typed token and token signing requirements extend to cover `force` as a signed flag, so a token signed with `force=False` cannot be replayed to trigger pre-clone deletion.

## Impact

- `transport/server.py` — `supply()` signature: add `force: bool = False`; pass it through to `_sign_upload_url` and include it in the response dict
- `transport/files.py` — `_transfer_upload()`, `_sign_upload_url()`, `_verify_file_token()`: include `force` in flags string; `_transfer_upload` adds `rm -rf <destination>` before clone when `force=True, bundle=True`
- `tests/unit/test_files.py` — new test class `BundleReseedForceTests` covering the force=True re-seed path
