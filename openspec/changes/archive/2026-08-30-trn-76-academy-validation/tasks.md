## 1. Implement _validate_academy()

- [x] 1.1 Add `_validate_academy()` function in `server.py` that returns a list of warning strings; use `_AGENTS_DIR` (line ~4662) for agents and `_get_orders_dir()` (line ~1356) for orders
- [x] 1.2 Validate every `*.json` in the agents path parses as JSON and has `name`, `description`, `tools` fields; collect a warning for each violation
- [x] 1.3 Validate every loaded manifest's explicit agent/skill/steering arrays reference only names that exist in the corresponding Academy pool; collect a warning for each unknown name
- [x] 1.4 Validate every `*.md` in the orders path has parseable YAML front-matter and at least one `{{...}}` placeholder; collect a warning for each violation
- [x] 1.5 Call `_validate_academy()` in the transport startup sequence and log each returned warning at `WARNING` level

## 2. Unit tests

- [x] 2.1 Add unit test: valid agent JSON with all required fields produces no warning
- [x] 2.2 Add unit test: agent JSON missing `tools` field produces a warning
- [x] 2.3 Add unit test: agent JSON that is not valid JSON produces a warning
- [x] 2.4 Add unit test: manifest referencing an unknown agent name produces a warning
- [x] 2.5 Add unit test: manifest with `"*"` produces no cross-reference warnings
- [x] 2.6 Add unit test: order template with valid front-matter and placeholder produces no warning
- [x] 2.7 Add unit test: order template missing `{{...}}` placeholder produces a warning

## 3. Verification

- [x] 3.1 Run `bash tests/run.sh --unit` — all tests pass
- [x] 3.2 Run `bash tests/run.sh --integration` — all tests pass
