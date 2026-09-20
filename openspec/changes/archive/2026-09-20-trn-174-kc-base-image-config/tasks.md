## 1. Add kc_base_image to Config

- [x] 1.1 In `transport/config.py`, add `kc_base_image: str = "ghcr.io/kirodotdev/kirocrew:0.6.0"` to the `Config` dataclass
- [x] 1.2 In `Config.from_env()`, add the mapping: `kc_base_image=os.environ.get("KC_BASE_IMAGE", "ghcr.io/kirodotdev/kirocrew:0.6.0")` (the string literal appears exactly twice in `config.py` — dataclass default and `from_env()` fallback — per spec)

## 2. Remove KC_BASE_IMAGE from lifecycle.py

- [x] 2.1 In `transport/lifecycle.py`, delete the module-level constant `KC_BASE_IMAGE = "ghcr.io/kirodotdev/kirocrew:0.6.0"` (L200)
- [x] 2.2 Replace all usages of `KC_BASE_IMAGE` in `lifecycle.py` with `cfg.kc_base_image` — confirm there are exactly two usages (L2005 comment and L2016 dict value); update both

## 3. Remove KC_BASE_IMAGE from server.py

- [x] 3.1 In `transport/server.py`, delete the module-level constant `KC_BASE_IMAGE = "ghcr.io/kirodotdev/kirocrew:0.6.0"` (L396)
- [x] 3.2 Check for usages of `KC_BASE_IMAGE` in `server.py` beyond the constant definition — as of this writing the constant is declared but never referenced in `server.py`, so simply deleting the declaration is sufficient; if usages exist, replace with `cfg.kc_base_image`

## 4. Update tests

- [x] 4.1 Search for all test patch targets referencing `KC_BASE_IMAGE`: `grep -rn "KC_BASE_IMAGE" tests/`
- [x] 4.2 For each patch site found, update to patch `transport.config.cfg` attribute or use `Config(kc_base_image="fake:test")` as appropriate for the test context
- [x] 4.3 Add a unit test confirming `Config.from_env()` respects the `KC_BASE_IMAGE` env var (i.e., `cfg.kc_base_image == "custom:latest"` when `KC_BASE_IMAGE=custom:latest`)

## 5. Verify

- [x] 5.1 Run `bash tests/run.sh --unit` — all tests pass
- [x] 5.2 Confirm `KC_BASE_IMAGE` no longer appears as a module-level constant in `lifecycle.py` or `server.py`: `grep -n "^KC_BASE_IMAGE" transport/lifecycle.py transport/server.py` returns zero results
- [x] 5.3 Confirm the string `"ghcr.io/kirodotdev/kirocrew:0.6.0"` appears exactly twice in `transport/config.py` (dataclass default + `from_env()`) and nowhere else in `transport/*.py`
