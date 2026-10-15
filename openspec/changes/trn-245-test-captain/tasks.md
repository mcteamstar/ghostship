## 1. Scaffolding

- [ ] 1.1 Create `tests/unit/test_captain.py` with a module docstring and the unittest import, relying on `tests/unit/conftest.py` for the `cryptography` stub
- [ ] 1.2 Import the helpers under test from `transport.captain` and the fakes (`FakePodmanClient`, `FakeArchiveResponse`, `_build_tar_with_file`) from `tests.fakes`
- [ ] 1.3 Add shared test helpers/fixtures (tmp-dir template builder, hex signing-seed constant)

## 2. _parse_order_front_matter

- [ ] 2.1 Test no front-matter returns whole content as body, empty description, empty aliases
- [ ] 2.2 Test `description: "Some text"` is parsed with surrounding quotes stripped
- [ ] 2.3 Test `aliases: ["a", "b"]` is parsed into `["a", "b"]`
- [ ] 2.4 Test body excludes the `---` fences and front-matter lines
- [ ] 2.5 Test unclosed front-matter fence is treated as no front-matter

## 3. _substitute_placeholders

- [ ] 3.1 Test `{{RAVEN_GATEWAY_ORIENTATION}}` is replaced with non-empty text
- [ ] 3.2 Test `{{RAVEN_SELF_CANCEL}}` is replaced
- [ ] 3.3 Test `{{RAVEN_STORE_RESOLUTION}}` is replaced
- [ ] 3.4 Test unknown `{{UNKNOWN_TOKEN}}` is left in place

## 4. _validate_captain_change_name

- [ ] 4.1 Test valid kebab-case name (`trn-245-test-captain`) passes without raising
- [ ] 4.2 Test uppercase letter raises `ValueError`
- [ ] 4.3 Test trailing hyphen raises `ValueError`
- [ ] 4.4 Test double hyphen raises `ValueError`
- [ ] 4.5 Test `None` input raises `ValueError`

## 5. _resolve_order_template

- [ ] 5.1 Test `None` template raises `ValueError`
- [ ] 5.2 Test unknown template name raises `ValueError`
- [ ] 5.3 Test valid template (from `_list_order_templates`) returns non-empty body with placeholders substituted; skip gracefully if no template exists
- [ ] 5.4 Test body containing both `<change>` and `<changes>` raises `ValueError` (tmp template dir)
- [ ] 5.5 Test template containing `<change>` with `change_name=None` raises `ValueError`

## 6. _format_captain_mail

- [ ] 6.1 Test returned message contains `From: admiral@localhost`, `To: captain@localhost`, `Subject:`, `Message-ID:`, `Date:` headers
- [ ] 6.2 Test second return value starts with `<` and ends with `@localhost>`
- [ ] 6.3 Test subject is derived from first non-empty line
- [ ] 6.4 Test subject is truncated to at most 72 characters
- [ ] 6.5 Test 32-byte hex `signing_secret` produces an `X-Admiral-Sig` header
- [ ] 6.6 Test newline-injected subject with signing raises `ValueError`
- [ ] 6.7 Test `supersedes_id` produces a `Supersedes:` header with that value
- [ ] 6.8 Test headers and body are separated by a blank line (`\n\n`)

## 7. _parse_sentinel_file

- [ ] 7.1 Test valid `key=value` content parses into the expected dict
- [ ] 7.2 Test empty content returns an empty dict
- [ ] 7.3 Test lines without `=` are skipped

## 8. _read_sentinel_file (FakePodmanClient)

- [ ] 8.1 Test returns decoded file content when a sentinel tar is scripted
- [ ] 8.2 Test returns `None` when the archive API raises

## 9. _captain_jobs and _captain_checkin_job

- [ ] 9.1 Test `_captain_jobs` returns an empty list for a non-list/malformed payload
- [ ] 9.2 Test `_captain_checkin_job` finds the matching `name="captain"`, `agent="raven"` job
- [ ] 9.3 Test `_captain_checkin_job` returns `None` for the wrong agent
- [ ] 9.4 Test `_captain_checkin_job` with `enabled_only=True` filters a disabled job

## 10. _mail_count (FakePodmanClient)

- [ ] 10.1 Test `"3 2"` output returns `5`
- [ ] 10.2 Test single-count `"7"` output returns `7`
- [ ] 10.3 Test unparseable output returns `0`

## 11. _captain_order_lock

- [ ] 11.1 Test same `crew_id` returns the same lock instance
- [ ] 11.2 Test different `crew_id`s return different lock instances

## 12. Verification

- [ ] 12.1 Run `tests/unit/test_captain.py` and confirm all tests pass
- [ ] 12.2 Confirm no production file under `transport/` was modified
