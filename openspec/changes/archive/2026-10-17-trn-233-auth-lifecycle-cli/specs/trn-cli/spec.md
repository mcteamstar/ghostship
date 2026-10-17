# Spec Delta

## MODIFIED Requirements

### Requirement: Auth subcommand group

The system SHALL provide a `ghostship auth` subcommand group of the form `ghostship auth <verb> [backend]`, where the verb is `login`, `logout` or `status` and the backend is `kiro`, `claude` or `codex`. It is the operator-facing command for supplying, replacing and clearing backend credentials; logins started by `launch` store into the same place. Running `ghostship auth` with no verb SHALL print usage help for the group and exit 0. `login` and `logout` SHALL require a backend; an unknown verb or backend SHALL print usage and exit non-zero.

All verbs SHALL accept:
- `--url <transport-url>` — override the transport base URL
- `--api-key <key>` — Bearer token for transports that require auth

#### Scenario: ghostship auth — no sub-subcommand
- **WHEN** `ghostship auth` is invoked with no verb
- **THEN** usage help for the `auth` group is printed and the process exits 0

#### Scenario: ghostship auth login — backend missing
- **WHEN** `ghostship auth login` is invoked with no backend
- **THEN** usage listing `kiro`, `claude` and `codex` is printed and the process exits non-zero

#### Scenario: ghostship auth login — unknown backend
- **WHEN** `ghostship auth login anthropic` is invoked
- **THEN** an error naming the valid backends is printed and the process exits non-zero, and no login flow is started

#### Scenario: ghostship auth login — success
- **WHEN** `ghostship auth login kiro` is invoked, a device-code method is chosen and the transport returns a device code response
- **THEN** the activation URL and user code are printed clearly, the CLI polls until auth completes, and "Authenticated successfully." is printed before exit 0

#### Scenario: ghostship auth login — already authenticated
- **WHEN** `ghostship auth login <backend>` is invoked and that backend already holds a credential
- **THEN** the current method is shown and the operator is asked to confirm replacing it before any method is run

#### Scenario: ghostship auth login — timeout
- **WHEN** `ghostship auth login <backend>` runs a device or authorisation-code flow and the user does not complete it within the polling window (default ~5 min)
- **THEN** a timeout message is printed that includes the activation URL again, and the process exits non-zero

#### Scenario: ghostship auth login — transport unreachable
- **WHEN** `ghostship auth login <backend>` is invoked and the transport URL is not reachable
- **THEN** a clear error message is printed (including the URL tried) and the process exits non-zero

#### Scenario: ghostship auth logout — success
- **WHEN** `ghostship auth logout claude` is invoked
- **THEN** claude's stored credential is cleared on the transport, "Logged out of claude." is printed, and the process exits 0

#### Scenario: ghostship auth logout — nothing stored
- **WHEN** `ghostship auth logout codex` is invoked and codex has no stored credential
- **THEN** the process exits 0

#### Scenario: ghostship auth logout — transport unreachable
- **WHEN** `ghostship auth logout <backend>` is invoked and the transport URL is not reachable
- **THEN** a clear error message is printed and the process exits non-zero

#### Scenario: ghostship auth login — custom URL
- **WHEN** `ghostship auth login kiro --url https://remote.example.com` is invoked
- **THEN** the auth flow targets that URL instead of the default

#### Scenario: ghostship auth login — GHOSTSHIP_URL env var
- **WHEN** `GHOSTSHIP_URL=http://my-host:64057` is set and `ghostship auth login kiro` is invoked without `--url`
- **THEN** the auth flow targets `http://my-host:64057`

## ADDED Requirements

### Requirement: Auth login offers per-backend methods interactively
`ghostship auth login <backend>` SHALL present a numbered menu of that backend's methods and act on the operator's choice. kiro: paste API key, device code with Builder ID (social login), device code with IAM Identity Center (enterprise). claude: authorisation code, paste API key, paste setup-token. codex: ChatGPT subscription (device code), paste API key. `--method <name>` SHALL select a method without the menu.

#### Scenario: Kiro menu
- **WHEN** `ghostship auth login kiro` is invoked on a terminal with no `--method`
- **THEN** the three kiro methods are listed and the operator is asked to choose one

#### Scenario: Codex menu
- **WHEN** `ghostship auth login codex` is invoked on a terminal with no `--method`
- **THEN** ChatGPT subscription and API key are listed and the operator is asked to choose one

#### Scenario: Method chosen by flag
- **WHEN** `ghostship auth login claude --method setup-token` is invoked
- **THEN** no menu is shown and the operator is prompted for the setup-token

#### Scenario: No terminal and no method
- **WHEN** `ghostship auth login kiro` is invoked with stdin not a terminal and no `--method`
- **THEN** an error asking for `--method` is printed and the process exits non-zero

### Requirement: Pasted secrets never taken from argv
For paste methods, the CLI SHALL read the secret from a hidden (no-echo) prompt when stdin is a terminal, or from stdin otherwise. The CLI SHALL NOT accept a credential value as a command-line argument, and SHALL NOT print it. On success it SHALL print the backend and method stored.

#### Scenario: Hidden prompt
- **WHEN** `ghostship auth login codex --method api-key` is run on a terminal
- **THEN** the key is read without echo, sent to the transport, and "Stored codex credential (api-key)." is printed

#### Scenario: Piped secret
- **WHEN** `printf '%s' "$TOKEN" | ghostship auth login claude --method setup-token` is run
- **THEN** the token is read from stdin and stored, with no prompt

#### Scenario: Empty secret
- **WHEN** an empty value is entered or piped
- **THEN** nothing is sent to the transport and the process exits non-zero

### Requirement: Auth login runs interactive flows to completion
For device-code and authorisation-code methods, the CLI SHALL start the transport flow, print the URL (and code, if any), and poll until completion. It SHALL print "Authenticated successfully." and exit 0 on completion.

#### Scenario: Kiro Builder ID login
- **WHEN** the operator picks device code with Builder ID
- **THEN** the device URL and code are printed, and on completion "Authenticated successfully." is printed and the process exits 0

#### Scenario: Codex ChatGPT login
- **WHEN** the operator picks ChatGPT subscription for codex
- **THEN** the device URL and one-time code are printed with a note that device code login must be enabled in the ChatGPT account or workspace security settings, and on completion "Authenticated successfully." is printed and the process exits 0

### Requirement: Identity Center login collects provider settings
For kiro `identity-center`, the CLI SHALL prompt for the IAM Identity Center start URL and region before starting the flow, defaulting to the transport's configured values, or take them from `--identity-provider` and `--region`. A missing value with stdin not a terminal SHALL exit non-zero before contacting the transport.

#### Scenario: Kiro Identity Center login
- **WHEN** the operator picks IAM Identity Center and enters a start URL and region
- **THEN** the flow is started with those values, the device URL and code are printed, and on completion the process exits 0

### Requirement: Claude authorisation code submitted by the CLI
For claude `oauth`, the CLI SHALL print the login URL, prompt for the code shown after approval without echoing it, submit it to the transport, and poll to completion.

#### Scenario: Claude authorisation code
- **WHEN** the operator picks authorisation code for claude
- **THEN** the login URL is printed, the operator is prompted for the code, the code is submitted without being echoed, and the CLI polls to completion

### Requirement: Login replaces an existing credential only after confirmation
When the backend already holds a credential, `ghostship auth login <backend>` SHALL show the current method and ask for confirmation before replacing it. `--yes` SHALL skip the confirmation. With stdin not a terminal and no `--yes`, it SHALL exit non-zero without changes.

#### Scenario: Replace confirmed
- **WHEN** claude holds an `api-key` and the operator runs `ghostship auth login claude`, picks setup-token and confirms
- **THEN** the setup-token replaces the API key

#### Scenario: Replace declined
- **WHEN** the operator declines the confirmation
- **THEN** nothing is sent to the transport and the process exits 0 with the old credential intact

### Requirement: Auth status
`ghostship auth status` SHALL print, for kiro, claude and codex, whether the backend is enabled, whether a credential is stored, its method, and when it was stored. It SHALL never print credential values. `--json` SHALL print the three per-backend status responses as one JSON object keyed by backend.

#### Scenario: Status table
- **WHEN** `ghostship auth status` is invoked and only claude holds a credential
- **THEN** three rows are printed, with claude showing its method and stored time and kiro and codex showing "not configured"

### Requirement: Transport URL and bearer key resolved consistently
Every CLI subcommand that calls the transport SHALL resolve its URL as `--url`, then `GHOSTSHIP_URL`, then the installed transport's configured host port, then `http://localhost:64057`. It SHALL resolve its bearer key as `--api-key`, then `GHOSTSHIP_API_KEY`, then the installed transport's `ga-api-key` file, if readable. An absent key SHALL send no `Authorization` header.

#### Scenario: Keyed local install needs no flags
- **WHEN** the transport was installed with a bearer key and `ghostship auth login kiro` is run with no `--api-key`
- **THEN** the CLI sends the installed key and the transport accepts the request

#### Scenario: Non-default port picked up
- **WHEN** the transport was installed with a non-default port and no `--url` or `GHOSTSHIP_URL` is given
- **THEN** the CLI targets the installed port

### Requirement: Secrets only sent over a protected connection
The CLI SHALL refuse to send a pasted secret or an authorisation code to a transport URL that is neither `https://` nor a loopback host (`localhost`, `127.0.0.0/8`, `::1`), unless `--insecure` is given. The refusal SHALL happen before the secret is read.

#### Scenario: Plain HTTP to a remote host
- **WHEN** `ghostship auth login claude --method api-key --url http://10.0.0.5:64057` is run without `--insecure`
- **THEN** the CLI exits non-zero with an error naming `https://` or `--insecure`, and does not prompt for the key

#### Scenario: Local plain HTTP allowed
- **WHEN** the resolved URL is `http://localhost:64057`
- **THEN** the secret is sent normally
