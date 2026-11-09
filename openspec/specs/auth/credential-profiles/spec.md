# Credential Profiles Specification

## Purpose

Manages named credential profiles per backend (kiro, claude, codex), allowing
multiple credentials to coexist under one backend so operators can switch between
them at launch time without re-authenticating.

## Requirements

### Requirement: Credential profiles are stored under a named sub-namespace

The system SHALL store each credential at `credentials/<backend>/<profile>.json`
where `profile` is an operator-supplied name. The `default` profile is used when
no profile is specified. Profile names MUST be 1–50 lowercase alphanumeric
characters or hyphens, starting and ending with an alphanumeric character.

#### Scenario: Store a named profile
- **WHEN** a credential is stored for backend `kiro` with profile `corp`
- **THEN** it is accessible via `get("kiro", profile="corp")` and does not affect any other profile

#### Scenario: Default profile used when profile is omitted
- **WHEN** a credential is stored without specifying a profile
- **THEN** it is stored under the `default` profile
- **AND** retrieving without a profile returns the same credential

#### Scenario: Invalid profile name rejected
- **WHEN** a credential store operation is attempted with a profile name that contains uppercase letters, spaces, or leading/trailing hyphens
- **THEN** the operation is rejected with a clear validation error before any write occurs

### Requirement: The profile name "default" is reserved and may not be supplied explicitly by users

`_validate_profile` SHALL raise `ValueError` when called with the value `"default"`,
citing it as a reserved name. HTTP handlers that receive `profile` from user-supplied
input (POST body fields or query-string parameters) SHALL return HTTP 400 when
`profile="default"` is explicitly provided by the caller. The value `"default"` is only
ever written internally — by the lazy migration path and as the implicit fallback when no
profile is specified. Internal call sites bypass the reserved-name check; see design.md D8
for the chosen approach.

#### Scenario: Explicit "default" rejected at the store layer
- **WHEN** a user-supplied operation calls `_validate_profile("default")`
- **THEN** a `ValueError` is raised with a message indicating `"default"` is reserved

#### Scenario: Explicit "default" in HTTP POST body returns 400
- **WHEN** `POST /login/kiro/api-key` is called with body `{"secret": "...", "profile": "default"}`
- **THEN** the response status is 400 with a message indicating the profile name is reserved

#### Scenario: Explicit "default" in HTTP query param returns 400
- **WHEN** `GET /login/kiro?profile=default` is called
- **THEN** the response status is 400 with a message indicating the profile name is reserved

#### Scenario: Internal migration still writes to "default" without error
- **WHEN** the lazy migration moves `credentials/kiro.json` → `credentials/kiro/default.json`
- **THEN** no validation error is raised — the migration bypasses the reserved-name check

### Requirement: Existing flat credentials are migrated transparently

When a flat `credentials/<backend>.json` file exists from a prior installation, the
system SHALL migrate it to `credentials/<backend>/default.json` on first access
without any operator action.

#### Scenario: Legacy file migrated on first read
- **WHEN** `get("kiro")` is called and `credentials/kiro.json` exists but `credentials/kiro/` does not
- **THEN** the file is moved to `credentials/kiro/default.json` and the credential is returned
- **AND** no data is lost

#### Scenario: Migration does not overwrite an existing default profile
- **WHEN** `credentials/kiro.json` and a valid `credentials/kiro/default.json` both exist
- **THEN** the flat file is removed and the profile directory file is kept

#### Scenario: Corrupt default preserves the legacy credential
- **WHEN** the default profile file is corrupt and a flat credential file exists
- **THEN** the flat file is preserved for recovery

### Requirement: Profile listing returns all stored profiles for a backend

The system SHALL provide a way to enumerate all stored profile names for a given
backend. The returned list MUST be sorted and MUST contain only profiles for which
a credential file exists.

#### Scenario: List profiles after storing two
- **WHEN** credentials are stored for backend `claude` under profiles `default` and `corp`
- **THEN** listing profiles for `claude` returns `["corp", "default"]` (sorted)

#### Scenario: List profiles for unconfigured backend returns empty list
- **WHEN** no credentials exist for `codex`
- **THEN** listing profiles for `codex` returns an empty list

### Requirement: Credential deletion targets a named profile

`delete(backend, profile)` SHALL remove only the credential for the specified
profile. Other profiles for the same backend MUST remain unaffected.

#### Scenario: Delete one profile leaves others intact
- **WHEN** `delete("kiro", profile="corp")` is called and `kiro/default` also exists
- **THEN** only `kiro/corp.json` is removed; `kiro/default.json` remains accessible

#### Scenario: Delete returns False for absent profile
- **WHEN** `delete("kiro", profile="nonexistent")` is called and no such file exists
- **THEN** `False` is returned and no error is raised

### Requirement: Status returns all profiles per backend without secret values

`status_all()` SHALL return a two-level map `{backend → {profile → status_dict}}`.
Each `status_dict` contains `configured`, `method`, `stored_at`, and `provider`
fields. No payload or secret value SHALL appear in the output.

#### Scenario: Status all shows each profile separately
- **WHEN** `kiro/default` and `kiro/corp` are both stored
- **THEN** `status_all()["kiro"]` contains entries for both `"default"` and `"corp"`
- **AND** neither entry contains the credential payload

#### Scenario: Status all shows unconfigured backend with empty profile map
- **WHEN** no credential exists for `codex`
- **THEN** `status_all()["codex"]` is an empty dict

### Requirement: HTTP GET /login/<backend> returns per-profile status

`GET /login/<backend>` SHALL accept an optional `?profile=<name>` query parameter
and return the status of the named profile. When the parameter is absent, it
returns the status of the `default` profile.

#### Scenario: Status for named profile returned
- **WHEN** `GET /login/kiro?profile=corp` is called and `kiro/corp` is stored
- **THEN** the response reports `configured: true` and the correct method for `corp`

#### Scenario: Default used when profile param absent
- **WHEN** `GET /login/kiro` is called with no `profile` param
- **THEN** the response reflects the `default` profile

### Requirement: HTTP POST /login/<backend>/<method> accepts a profile in the request body

All pasted-secret and device-flow login routes SHALL accept an optional `profile`
field in the JSON request body. When absent, the credential is stored under
`default`. The stored credential is associated with the named profile.

#### Scenario: Pasted API key stored under named profile
- **WHEN** `POST /login/kiro/api-key` with body `{"secret": "...", "profile": "corp"}`
- **THEN** the credential is accessible as `kiro/corp` and not under `kiro/default`

#### Scenario: Device flow stores under named profile on completion
- **WHEN** a device-flow login for `kiro/builder-id` was initiated with `profile: "corp"` and completes
- **THEN** the resulting credential is stored as `kiro/corp`

### Requirement: HTTP POST /logout/<backend> accepts a profile target

`POST /logout/<backend>` SHALL accept an optional `profile` query parameter.
When specified, only that profile's credential is cleared. When absent, the
`default` profile is targeted.

#### Scenario: Named profile cleared on logout
- **WHEN** `POST /logout/kiro?profile=corp` is called
- **THEN** `kiro/corp` is removed; `kiro/default` is unaffected

#### Scenario: Default profile cleared when no profile specified
- **WHEN** `POST /logout/kiro` is called without a `profile` param
- **THEN** `kiro/default` is removed

### Requirement: HTTP GET /login/<backend>/profiles lists stored profiles

A new route `GET /login/<backend>/profiles` SHALL return a sorted list of
profile names for the backend for which credentials exist.

#### Scenario: Profiles listed
- **WHEN** `GET /login/kiro/profiles` is called and `kiro/default` and `kiro/corp` exist
- **THEN** the response body is `{"profiles": ["corp", "default"]}`

#### Scenario: Empty list for unconfigured backend
- **WHEN** `GET /login/codex/profiles` is called and no codex credentials exist
- **THEN** the response body is `{"profiles": []}`

### Requirement: ghostship auth login accepts --profile

`ghostship auth login <backend> --profile <name>` SHALL pass the profile to the
login route so the credential is stored under that name. When `--profile` is
omitted, the credential is stored under `default`.

#### Scenario: Named profile stored via CLI
- **WHEN** `ghostship auth login kiro --method api-key --profile corp` is run and a key is entered
- **THEN** the credential is stored as `kiro/corp` on the transport

#### Scenario: Default used when --profile omitted
- **WHEN** `ghostship auth login kiro --method api-key` is run
- **THEN** the credential is stored as `kiro/default`

### Requirement: ghostship auth status lists all profiles grouped by backend

`ghostship auth status` SHALL display every stored profile for each backend.
In `--json` mode the output is the full `status_all()` map. In human mode,
each backend section lists its profiles with method and stored-at time.

#### Scenario: Multiple profiles shown in human output
- **WHEN** `kiro/default` and `kiro/corp` are both stored and `ghostship auth status` is run
- **THEN** the output shows both profiles under the `kiro` section

#### Scenario: JSON mode returns structured data
- **WHEN** `ghostship auth status --json` is run
- **THEN** the output is a JSON object where each backend key maps to a dict of profile names

### Requirement: ghostship auth logout accepts --profile

`ghostship auth logout <backend> --profile <name>` SHALL target only the named
profile. When `--profile` is omitted, the `default` profile is targeted.

#### Scenario: Named profile removed via CLI
- **WHEN** `ghostship auth logout kiro --profile corp` is run
- **THEN** `kiro/corp` is removed; other kiro profiles are unaffected

### Requirement: Launch response reports the resolved credential profile

A successful crew launch SHALL return its resolved `acp_profile`, matching the credential profile recorded for the crew, whether selected explicitly or resolved implicitly.

#### Scenario: Explicit named profile
- **WHEN** a crew launches successfully with a named credential profile
- **THEN** the launch response and crew registry identify that same profile

#### Scenario: Implicit profile selection
- **WHEN** a crew launches successfully with an implicitly resolved profile
- **THEN** the launch response reports the actual resolved profile

### Requirement: OAuth credential payloads are isolated by profile

OAuth credentials used for launch, refresh and propagation to existing crews SHALL come from the resolved backend and profile. A named profile SHALL NOT silently receive another profile's credential or a shared default archive. Supported legacy default-profile credentials SHALL remain usable through a safe, idempotent migration or explicit default-only compatibility path.

#### Scenario: Two OAuth profiles
- **WHEN** two profiles of the same backend contain distinct OAuth payloads and a crew selects one
- **THEN** only the selected profile's payload is injected into that crew

#### Scenario: Reauthentication targets one profile
- **WHEN** an OAuth login or refresh completes for one profile
- **THEN** other profiles and crews assigned to them retain their credentials

#### Scenario: Named profile lacks a usable credential
- **WHEN** a named profile has no valid stored payload
- **THEN** the operation reports an error without falling back to a shared or default credential

#### Scenario: Existing legacy default credential
- **WHEN** an operator has only a supported legacy default OAuth credential
- **THEN** the default profile can use it without overwriting a newer profile-scoped credential

### Requirement: OAuth login persistence failures are visible

The system SHALL report OAuth login success only after the selected profile's credential has been durably stored. If persistence fails, the system SHALL report failure and retain enough pending state to retry or explicitly recover, without leaking credentials or claiming completion.

#### Scenario: Profile write fails
- **WHEN** the selected profile credential cannot be saved after OAuth completes
- **THEN** login reports an error rather than success and does not replace another profile's credential

#### Scenario: Retry after transient failure
- **WHEN** the profile write succeeds on a subsequent retry of the same valid pending flow
- **THEN** login reports success and the credential belongs only to the selected profile
