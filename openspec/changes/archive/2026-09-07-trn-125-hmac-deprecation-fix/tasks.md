## 1. Fix call sites in transport/files.py

- [x] 1.1 Replace `hmac.new(_FILE_SECRET.encode(), payload.encode(), hashlib.sha256)` at line 184 with `hmac.new(_FILE_SECRET.encode(), payload.encode(), digestmod=hashlib.sha256)`
- [x] 1.2 Replace `hmac.new(_FILE_SECRET.encode(), payload.encode(), hashlib.sha256)` at line 224 with `hmac.new(_FILE_SECRET.encode(), payload.encode(), digestmod=hashlib.sha256)`
- [x] 1.3 Replace `hmac.new(_FILE_SECRET.encode(), payload.encode(), hashlib.sha256)` at line 242 with `hmac.new(_FILE_SECRET.encode(), payload.encode(), digestmod=hashlib.sha256)`

## 2. Fix call site in transport/captain.py

- [x] 2.1 Update the multi-line `hmac.new(signing_secret.encode(), ..., hashlib.sha256,)` at line 227 to use `digestmod=hashlib.sha256` as a keyword argument

## 3. Fix call site in transport/container_scripts/inject_policy.py

- [x] 3.1 Replace `hmac.new(secret.encode("utf-8"), payload, hashlib.sha256)` at line 52 with `hmac.new(secret.encode("utf-8"), payload, digestmod=hashlib.sha256)`

## 4. Verify and commit

- [x] 4.1 Run `grep -rn "hmac.new" transport/` to confirm zero remaining call sites use the deprecated form without an explicit `digestmod=` keyword
- [x] 4.2 Run the existing test suite (`pytest` or equivalent) and confirm no regressions
- [x] 4.3 Commit with message: `fix(transport): replace deprecated hmac.new() with explicit digestmod= (TRN-125)`
