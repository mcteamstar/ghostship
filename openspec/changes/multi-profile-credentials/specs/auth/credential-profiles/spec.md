# Spec Delta

## Purpose

Manages named credential profiles per backend (kiro, claude, codex), allowing
multiple credentials to coexist under one backend so operators can switch between
them at launch time without re-authenticating.

## ADDED Requirements

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

### Requirement: Existing flat credentials are migrated transparently

When a flat `credentials/<backend>.json` file exists from a prior installation, the
system SHALL migrate it to `credentials/<backend>/default.json` on first access
without any operator action.

#### Scenario: Legacy file migrated on first read
- **WHEN** `get("kiro")` is called and `credentials/kiro.json` exists but `credentials/kiro/` does not
- **THEN** the file is moved to `credentials/kiro/default.json` and the credential is returned
- **AND** no data is lost

#### Scenario: Migration does not overwrite an existing default profile
- **WHEN** `credentials/kiro.json` and `credentials/kiro/default.json` both exist
- **THEN** the flat file is removed and the profile directory file is kept

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
