# Spec Delta

## REMOVED Requirements

### Requirement: Claude OAuth token configured by the operator
**Reason**: The setup-token is no longer set in `ghostship.conf`; it is one of the methods of `ghostship auth login claude` and stored by the transport's credential store.
**Migration**: None (breaking). Run `ghostship auth login claude --method setup-token`; an existing `ga-claude-code-oauth-token` secret or `CLAUDE_CODE_OAUTH_TOKEN` conf line is ignored.

### Requirement: Claude OAuth token injected into crew containers
**Reason**: Superseded by backend-credentials "Credential delivered to crews according to its method", which sets `CLAUDE_CODE_OAUTH_TOKEN` when claude's active method is `setup-token`.
**Migration**: None; behaviour for a stored setup-token is unchanged.

### Requirement: Claude credential precedence
**Reason**: Replaced by backend-credentials "One active credential per backend": storing any Claude credential replaces the previous one, so no precedence applies.
**Migration**: Choose the method with `ghostship auth login claude`.

### Requirement: Claude OAuth token satisfies the launch auth check
**Reason**: Superseded by backend-credentials "Launch starts the backend's interactive login when no credential is stored", under which any stored Claude credential, whichever method, lets launch proceed.
**Migration**: None.

### Requirement: Claude OAuth token reported as inert when claude is disabled
**Reason**: Superseded by agent-backends "Settings for disabled backends are reported as inert", which now covers stored credentials.
**Migration**: None.
