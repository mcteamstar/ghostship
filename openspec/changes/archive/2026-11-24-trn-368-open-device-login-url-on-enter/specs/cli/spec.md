# Spec Delta

## MODIFIED Requirements

### Requirement: Auth login runs interactive flows to completion
For device-code and authorisation-code methods, the CLI SHALL start the transport flow, print the URL (and code, if any), and poll until completion. It SHALL print "Authenticated successfully." and exit 0 on completion. During an interactive device-code flow with a login URL, it SHALL show that Enter opens the URL in the default browser; pressing Enter SHALL open it while polling continues. A browser-launch failure SHALL NOT stop polling.

#### Scenario: Kiro Builder ID login
- **WHEN** the operator picks device code with Builder ID
- **THEN** the device URL and code are printed, and on completion "Authenticated successfully." is printed and the process exits 0

#### Scenario: Codex ChatGPT login
- **WHEN** the operator picks ChatGPT subscription for codex
- **THEN** the device URL and one-time code are printed with a note that device code login must be enabled in the ChatGPT account or workspace security settings, and on completion "Authenticated successfully." is printed and the process exits 0

#### Scenario: Enter opens the device login URL
- **WHEN** the operator presses Enter during an interactive device-code login that has a login URL
- **THEN** the CLI opens that URL in the default browser and continues polling for authentication completion

#### Scenario: Enter retries opening the device login URL
- **WHEN** the operator presses Enter again during the same device-code login
- **THEN** the CLI attempts to open the same login URL again and continues polling

#### Scenario: Browser launch fails
- **WHEN** the operator presses Enter during device-code login and the default browser cannot be opened
- **THEN** the CLI reports the launch failure, keeps the printed URL available for manual use, and continues polling

#### Scenario: Non-interactive device-code login
- **WHEN** device-code login runs with stdin that is not a terminal
- **THEN** the CLI does not wait for keyboard input and continues polling as before

#### Scenario: Authorisation-code login retains its code prompt
- **WHEN** the operator chooses an authorisation-code login method
- **THEN** the CLI retains its existing URL display and code-submission behavior without the device-code Enter hint
