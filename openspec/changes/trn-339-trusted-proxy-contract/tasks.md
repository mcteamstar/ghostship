# Tasks

## 1. Update the trusted-proxy contract

- [x] 1.1 Replace the obsolete trusted-proxy section in the rate-limiting spec with CIDR peer-trust and first-hop behavior; verify every scenario matches transport/auth.py.
- [x] 1.2 Correct the GA_TRUSTED_PROXY_CIDR configuration entry, rate-limit operator explanation, and installation configuration-docs contract; verify names and behavior against transport/config.py and middleware code.
- [x] 1.3 Add or update focused tests for trusted peer, untrusted peer, absent forwarded header, and multiple-hop behavior; run rate-limit unit tests.

## 2. Verify the contract

- [x] 2.1 Search active specs and docs for obsolete GA_TRUSTED_PROXY and last-hop claims; verify no stale active guidance remains.
