## 1. Create container_scripts/ directory and script files

- [ ] 1.1 Create `transport/container_scripts/` directory
- [ ] 1.2 Create `inject_auth.py` — SQLite INSERT auth rows; accepts db_path and b64_rows as argv
- [ ] 1.3 Create `read_auth.py` — SELECT auth_kv rows, return b64 JSON; accepts db_path as argv
- [ ] 1.4 Create `wipe_auth.py` — DELETE auth_kv rows; accepts db_path as argv
- [ ] 1.5 Create `append_captain_mail.py` — write a mail message to the captain Maildir; accepts message content via stdin
- [ ] 1.6 Create `read_mail_counts.py` — count unread messages in each mailbox; accepts mailbox list as argv JSON
- [ ] 1.7 Create `read_mail_subjects.py` — read subject lines from mailboxes (replaces b64-exec `_read_subjects_src`); accepts mailbox list as argv JSON
- [ ] 1.8 Create `patch_models.py` — glob agent JSONs and update model field; accepts model value as argv
- [ ] 1.9 Create `patch_crew_config.py` — write config.local.json overrides; accepts config values as argv or stdin JSON
- [ ] 1.10 Create `inject_policy.py` — write admission_policy.json; accepts policy JSON via stdin
- [ ] 1.11 Create `inject_admiral_secret.py` — write admiral secret to file with fsync; accepts secret and path as argv
- [ ] 1.12 Create `check_gateway_ready.py` — check if kirocrew*.json files exist; exits 0 if ready, 1 if not
- [ ] 1.13 Create `copy_steering.py` — copy steering files into place; accepts src and dest as argv
- [ ] 1.14 Create `transfer_raw.py` — raw file transfer operation (from `_RAW_TRANSFER_SCRIPT`)
- [ ] 1.15 Create `transfer_cleanup.py` — cleanup transfer staging area (from `_CLEANUP_TRANSFER_SCRIPT`)

## 2. Update Containerfile

- [ ] 2.1 Add `COPY container_scripts/ /scripts/` to `transport/Containerfile` so scripts are baked into the image

## 3. Replace python3 -c call sites in server.py

- [ ] 3.1 Replace `_inject_auth` call site (line ~2332) with `python3 /scripts/inject_auth.py`
- [ ] 3.2 Replace `_read_auth_from_crew` call site (line ~2673) with `python3 /scripts/read_auth.py`
- [ ] 3.3 Replace `_handle_logout_post` wipe call site (line ~3036) with `python3 /scripts/wipe_auth.py`
- [ ] 3.4 Replace `_append_captain_mail` call site (line ~1576) with `python3 /scripts/append_captain_mail.py`
- [ ] 3.5 Replace `_read_all_mail_counts` call site (line ~1640) with `python3 /scripts/read_mail_counts.py`
- [ ] 3.6 Replace `_read_all_mail_subjects` b64-exec call site (line ~1700) with `python3 /scripts/read_mail_subjects.py` — eliminate `_read_subjects_src` and `base64.b64encode` workaround
- [ ] 3.7 Replace `_patch_models` call site (line ~2629) with `python3 /scripts/patch_models.py`
- [ ] 3.8 Replace `_patch_crew_config` call site (line ~3318) with `python3 /scripts/patch_crew_config.py`
- [ ] 3.9 Replace `_inject_policy` call site (line ~3395) with `python3 /scripts/inject_policy.py`
- [ ] 3.10 Replace admiral secret injection call site (line ~3436) with `python3 /scripts/inject_admiral_secret.py`
- [ ] 3.11 Replace gateway readiness check call site (line ~3472) with `python3 /scripts/check_gateway_ready.py`
- [ ] 3.12 Replace `_copy_steering` call site (line ~2572) with `python3 /scripts/copy_steering.py`
- [ ] 3.13 Replace transfer script call sites (lines ~5239, ~5279) with `python3 /scripts/transfer_raw.py` and `python3 /scripts/transfer_cleanup.py`
- [ ] 3.14 Verify no `python3 -c` calls remain in `server.py`; remove now-unused constants (`_RAW_TRANSFER_SCRIPT`, `_ARCHIVE_TRANSFER_SCRIPT`, `_CLEANUP_TRANSFER_SCRIPT`, `_read_subjects_src`)

## 4. Unit tests

- [ ] 4.1 Add tests for `inject_auth.py` — inserts rows into a temp SQLite DB
- [ ] 4.2 Add tests for `read_auth.py` — reads rows; returns None equivalent for empty/registration-only DB (aligns with TRN-78 Bug 1 fix)
- [ ] 4.3 Add tests for `wipe_auth.py` — deletes rows from temp SQLite DB
- [ ] 4.4 Add tests for `read_mail_counts.py` — counts messages in a mock Maildir tree
- [ ] 4.5 Add tests for `read_mail_subjects.py` — reads subjects from a mock Maildir tree
- [ ] 4.6 Add tests for `patch_models.py` — updates model field in mock agent JSON files

## 5. Verification

- [ ] 5.1 Run `bash tests/run.sh --unit` — all tests pass
- [ ] 5.2 Run `bash tests/run.sh --integration` — all tests pass
