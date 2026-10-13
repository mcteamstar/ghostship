# Spec Delta

## ADDED Requirements

### Requirement: Credential injection uses container_archive_put, not shell exec
The transport SHALL deliver credential files into crew containers via `container_archive_put` (atomic tar write) rather than `sh -c` shell exec. This applies to: Claude OAuth credential injection (`_inject_claude_auth`), Codex credential injection (`_inject_codex_auth`), and dashboard cookie injection (`_write_dashboard_cookie`). No credential injection path SHALL use `sh -c`, `python3 -c`, or any other inline shell or interpreter exec to write credential content.

#### Scenario: Claude auth injection does not use shell exec
- **WHEN** `_inject_claude_auth` is called to deliver credentials into a crew container
- **THEN** the credentials are written via `container_archive_put` as a tar member; no `sh -c` or `printf` subprocess is spawned

#### Scenario: Dashboard cookie injection does not use inline python exec
- **WHEN** `_write_dashboard_cookie` is called to write the cookie into a crew container
- **THEN** the cookie value is written via `container_archive_put`; no `python3 -c` subprocess is spawned

### Requirement: Config repr masks sensitive credential fields
The `Config` dataclass SHALL override `__repr__` to replace the values of sensitive fields with `***`. Sensitive fields include: `kiro_api_key`, `anthropic_api_key`, `openai_api_key`, `claude_code_oauth_token`. Any log call that includes `repr(cfg)` or `str(cfg)` SHALL NOT emit live credential values.

#### Scenario: Config repr does not expose API keys
- **WHEN** `repr(cfg)` is called on a populated `Config` instance
- **THEN** the returned string contains `***` in place of any non-empty credential field value
