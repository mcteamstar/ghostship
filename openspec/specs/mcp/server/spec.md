# MCP Server Specification

## Purpose

Expose crew orchestration to any MCP client as a single streamable-HTTP server (`ghostship`), covering the tool/resource surface, transport wiring, and discoverability — as distinct from what each tool does internally (see the `crew-lifecycle/`, `task-orchestration/`, and `file-transfer/` capability groups).

## Requirements

### Requirement: Streamable-HTTP MCP transport on a configurable port
The transport SHALL serve streamable HTTP MCP at `0.0.0.0:64057` without publishing a host port; `HOST`/`PORT` control only the portal's host binding. Empty `GA_API_KEY` preserves current trust; otherwise every MCP request SHALL pass Bearer validation before processing.

#### Scenario: Default bind address for containerised install
- **WHEN** the transport starts inside a container with `HOST` unset
- **THEN** the MCP server is reachable through `ga-portal` only from localhost on the host, not from other network hosts

#### Scenario: Non-containerised loopback binding
- **WHEN** the operator sets `HOST=127.0.0.1`
- **THEN** the MCP server is reachable through `ga-portal` on host loopback only and not from the local network, while the transport itself still listens on `0.0.0.0` inside its container so `ga-portal` can reach it at `ga-transport:64057`

#### Scenario: Default port
- **WHEN** the transport process starts with no `PORT` override and `GA_API_KEY` unset or empty
- **THEN** the MCP server listens on `64057` using the `streamable-http` transport in stateless mode and accepts requests as before

#### Scenario: Custom port
- **WHEN** the operator sets `PORT=9000`
- **THEN** `ga-portal` publishes on host port `9000`, the transport continues to listen on `64057` internally, and the client-facing URL for registration is `http://localhost:9000/mcp`

#### Scenario: API-key authentication enabled
- **WHEN** the transport process starts with a non-empty `GA_API_KEY` and an MCP request includes exactly one `Authorization` header using the `Bearer` scheme with that configured value
- **THEN** the request reaches the MCP application and can complete normally

#### Scenario: Missing or invalid API key
- **WHEN** the transport process starts with a non-empty `GA_API_KEY` and an MCP request omits, misformats, duplicates, or supplies an incorrect bearer credential
- **THEN** the transport responds with `401 Unauthorized` and `WWW-Authenticate: Bearer`, and the MCP application does not process the request

#### Scenario: Client registration carries the key as a header
- **WHEN** a user registers the server with an MCP client while API-key authentication is enabled
- **THEN** the client points at `http://localhost:<PORT>/mcp` and sends `Authorization: Bearer <GA_API_KEY>` on initialization and subsequent MCP HTTP requests

### Requirement: Agent roster resource
The system SHALL expose a `transport://agents` MCP resource that lists every agent JSON found in the `/agents` bind-mount, formatted for a client to read before calling `dispatch`.

#### Scenario: Agents present
- **WHEN** `transport://agents` is read and `/agents` contains one or more valid agent JSON files
- **THEN** the response is a plain-text roster with one heading per agent, each showing that agent's `name` and `description` fields

#### Scenario: A malformed agent file
- **WHEN** one file under `/agents` cannot be parsed as JSON
- **THEN** that entry is listed with a placeholder noting it could not be read, rather than failing the whole resource read

#### Scenario: No agents bind-mount
- **WHEN** `/agents` does not exist in the transport container
- **THEN** the resource returns a message stating no agents directory was found, rather than raising an error

### Requirement: Order template resource

The MCP server SHALL expose `transport://orders` as a name and one-line-description index and `transport://orders/{name}` as the complete resolved template body used by `captain(action="order")`, with substitutions applied and front matter removed. Unknown names SHALL return an error; both resources SHALL work without a running crew.

#### Scenario: Templates present
- **WHEN** `transport://orders` is read and one or more templates are available
- **THEN** the response is a plain-text summary index — one entry per template showing the template name and its one-line description; the full template body text is NOT included

#### Scenario: Reading the resource requires no crew
- **WHEN** `transport://orders` or `transport://orders/{name}` is read
- **THEN** the response does not depend on any crew existing or being reachable, since templates are static transport-side content

#### Scenario: transport://orders/{name} returns full resolved body
- **WHEN** `transport://orders/sdd` is read
- **THEN** the response contains the complete resolved body of the `sdd` template with all `{{PLACEHOLDER}}` tokens substituted, and without the YAML front-matter block

#### Scenario: transport://orders/{name} for unknown template
- **WHEN** `transport://orders/nonexistent` is read
- **THEN** the resource returns an error indicating the template was not found, rather than an empty or partial response

#### Scenario: User-defined template appears in summary index
- **WHEN** `GA_ORDERS_DIR` is set, a user-defined template named `my-workflow` exists in that directory, and `transport://orders` is read
- **THEN** `my-workflow` appears in the summary index alongside built-in templates

#### Scenario: User-defined template is readable via per-template resource
- **WHEN** `GA_ORDERS_DIR` is set, a user-defined template named `my-workflow` exists, and `transport://orders/my-workflow` is read
- **THEN** the response contains the full resolved body of `my-workflow`

### Requirement: Client-facing server identity
The system SHALL identify itself to MCP clients as `transport` (server name) while the convention across this project's docs and registration commands is to register the connection under the client-side name `ghostship`.

#### Scenario: Registering with a harness
- **WHEN** a user registers this server with an MCP client (kiro-cli, Claude Code, or any other streamable-HTTP-capable client)
- **THEN** they name the connection `ghostship` and point it at `http://localhost:<PORT>/mcp`, per the README's registration examples

### Requirement: Tool descriptions reinforce workflow order and make tool relationships explicit

Tool descriptions SHALL teach `launch → supply → dispatch → pickup/steer → evac → nuke`: supply before repo work, empty-workspace risk, task-string context, steer's running/completed distinction, evac/supply pairing, and nuke's irreversibility after evac. `captain` is the Raven autopilot alternative. The server description SHALL name the sequence; signatures, runtime, grouping, and discovery order are unchanged.

#### Scenario: A core tool description names its workflow step

- **WHEN** an MCP client lists tools on the `ghostship` connection and reads the
  description of any of `launch`, `supply`, `dispatch`, `pickup`, `steer`,
  `evac`, or `nuke`
- **THEN** that description names the tool's position in the
  launch → supply → dispatch → pickup/steer → evac → nuke sequence

#### Scenario: Sequencing guardrails are stated in the descriptions that need them

- **WHEN** the `supply` and `nuke` descriptions are read
- **THEN** `supply` states that dispatching into an unsupplied crew is a real
  failure mode, and `nuke` states that `evac` must precede it because teardown
  is irreversible

#### Scenario: Tool relationships are explicit, not implied

- **WHEN** the `dispatch`, `pickup`, `steer`, `evac`, and `captain` descriptions
  are read
- **THEN** `dispatch` names `pickup` as the next step, `pickup` names its
  relationship to `steer`, `evac` names its pairing with `supply`, and
  `captain` names its relationship to the manual dispatch/pickup/steer relay

#### Scenario: Server-level description names the sequence

- **WHEN** a client reads the top-level MCP server `description=` field
- **THEN** it names the workflow sequence
  (launch → supply → dispatch → pickup → steer → evac → nuke) explicitly, rather
  than listing tools with no ordering

#### Scenario: Description edits do not alter behavior

- **WHEN** the tool descriptions are revised to satisfy this requirement
- **THEN** no tool signature, argument, return shape, or runtime behavior
  changes, and the set and ordering of tools returned by tool discovery is
  unchanged

### Requirement: Tool surface covers the full crew lifecycle
MCP SHALL expose workspace tools in order (`crews`, `launch`, `supply`, `evac`, `nuke`), then agent tools (`captain`, `dispatch`, `schedule`, `steer`, `pickup`, `bridge`). The public HTTP surface SHALL also include `GET /openapi.json`; it is not an MCP tool.

#### Scenario: Tool discovery
- **WHEN** an MCP client lists tools on the `ghostship` connection
- **THEN** it sees all eleven tools above, in that order, and no others, including `bridge` with the docstring-derived description used for model tool selection

#### Scenario: OpenAPI schema discoverable without MCP client
- **WHEN** an HTTP GET request is made to `/openapi.json` on the transport port
- **THEN** the response is a valid OpenAPI 3.x JSON document describing the transport's full HTTP surface, accessible without an MCP client or authentication

### Requirement: Version resource exposes transport and crew image versions
The system SHALL expose a `transport://version` MCP resource that returns the transport process version and, for each running crew, the crew image version. The transport version SHALL be read from a `VERSION` file at the repository root at startup. The crew image version SHALL be read from the crew container's OCI label `org.ghostship.version` at crew launch time and stored in the registry.

#### Scenario: Version resource with no crews running
- **WHEN** `transport://version` is read and no crews are registered
- **THEN** the response is a JSON object containing `transport` set to the semver string from the `VERSION` file, and `crews` as an empty object

#### Scenario: Version resource with crews running
- **WHEN** `transport://version` is read and one or more crews are registered
- **THEN** the response is a JSON object containing `transport` set to the transport semver, and `crews` as an object keyed by `crew_id` each with a `crew_image_version` field read from the registry

#### Scenario: VERSION file missing at startup
- **WHEN** the transport process starts and no `VERSION` file exists at the repository root
- **THEN** the transport version SHALL default to `"0.0.0-dev"` and the resource SHALL still be available

#### Scenario: Crew image has no version label
- **WHEN** a crew is launched from an image that does not carry the `org.ghostship.version` OCI label
- **THEN** the registry stores `crew_image_version` as `"unknown"` for that crew, and `transport://version` reports it as such

### Requirement: HTTP health endpoint includes version
The system SHALL include the transport version in the MCP server's HTTP response headers or a dedicated `GET /version` route on the MCP port, so that monitoring tools and operators can query the running version without an MCP client.

#### Scenario: GET /version returns JSON
- **WHEN** an HTTP GET request is made to `/version` on the MCP port
- **THEN** the response is `200 OK` with `Content-Type: application/json` and a body containing at minimum `{"transport": "<semver>"}`

#### Scenario: Unauthenticated access when API key is set
- **WHEN** `GA_API_KEY` is configured and a GET request to `/version` omits the bearer token
- **THEN** the response is `200 OK` — the version endpoint SHALL NOT require authentication, as version information is not sensitive

### Requirement: Host memory visibility in crews() response

The `crews()` MCP endpoint SHALL include a top-level
`host_memory_available_gb` field (float, rounded to 1 decimal) in its JSON
response, representing the current available memory as reported by the Podman
info API.

The value SHALL be cached for up to 5 seconds to avoid per-call Podman API
overhead.

#### Scenario: crews() returns memory field
- **WHEN** a client calls the `crews()` endpoint
- **THEN** the response includes `"host_memory_available_gb": <float>` at the top level alongside the crew list

#### Scenario: Cached value within TTL
- **WHEN** two `crews()` calls are made within 5 seconds
- **THEN** only one Podman info API call is made; the second response uses the cached value

#### Scenario: Podman info unavailable
- **WHEN** the Podman info API call fails
- **THEN** `host_memory_available_gb` is set to `null` and the rest of the response is unaffected

### Requirement: Transport exposes a single port

The transport SHALL bind to a single port for all operations: MCP, REST, and
file transfer. A second file-server port SHALL NOT exist. The single port SHALL
be configurable via `GA_PORT` (default 8000).

#### Scenario: All operations on one port
- **WHEN** a client connects to the transport's single port
- **THEN** MCP (`/mcp`), REST (`/login`, `/logout`, `/health`, `/version`), and file transfer (`/files/*`) are all available at that port

#### Scenario: No second port
- **WHEN** the transport starts
- **THEN** only one port is bound; no service listens on `PORT+1`

### Requirement: Single public URL configuration

The transport SHALL accept a single `GA_HOST_URL` environment variable as the
base URL for all externally-reachable endpoints. Presigned file URLs
(supply and evac) SHALL use `GA_HOST_URL` as their base.

#### Scenario: Presigned URLs use GA_HOST_URL
- **WHEN** the Admiral calls `evac()` or `supply()`
- **THEN** the returned URL uses `GA_HOST_URL` as its base (e.g. `https://my-host.example.com/files/...`)

### Requirement: crews() response shape
`crews()` SHALL return a top-level `crews` array with each crew's ID, container, status, canonical `comp` and compatibility `composition`, timestamps, uptime, health, image version, dashboard URL, policy version, and tracked agents (`task_id`, `agent`, `done`, `elapsed_secs`; never `last_tool`). Include host memory and active/max counts at top level. Legacy `composition` supplies missing `comp`; on mismatch, `comp` wins and the mismatch is logged.

#### Scenario: Response fields retain their types and nullability
- **WHEN** `crews()` returns a fleet payload
- **THEN** each crew entry uses strings for `crew_id`, `container`, `comp`, `composition`, `created_at`, and `crew_image_version`; `status` is `running` or `stopped`; `last_task_at` and `dashboard_url` are strings or null; `uptime_secs` is an integer or null; `gateway_healthy` is boolean; and `agents` is an array with string `task_id`/`agent`, boolean `done`, and numeric `elapsed_secs`. `policy_version` is an integer when present. At top level, `host_memory_available_gb` is a number or null and `active_crews`/`max_active_crews` are integers.

#### Scenario: crews() omits last_tool from agent entries
- **WHEN** `crews()` is called and one or more agents are listed for a crew
- **THEN** each agent entry contains `task_id`, `agent`, `done`, and `elapsed_secs`, and does not contain `last_tool`

#### Scenario: Running crew includes uptime_secs when inspect succeeds
- **WHEN** `crews()` is called and a crew has `status == "running"` with a valid Podman start time
- **THEN** that crew's entry includes an `uptime_secs` integer reflecting seconds since its container started

#### Scenario: stopped crew omits uptime_secs
- **WHEN** `crews()` is called and a crew has `status == "stopped"`
- **THEN** its `uptime_secs` is absent or null

#### Scenario: last_task_at populated when tasks have been dispatched
- **WHEN** at least one task has been dispatched to a crew
- **THEN** that crew's `last_task_at` is an ISO 8601 timestamp for the most recent dispatch

#### Scenario: last_task_at is null for crews with no task history
- **WHEN** a crew has never had a task dispatched
- **THEN** its `last_task_at` is null

#### Scenario: Crew entry exposes comp and equal compatibility alias
- **WHEN** a crew was launched with `comp="spec-ops"`
- **THEN** its entry includes `"comp": "spec-ops"` and `"composition": "spec-ops"`

#### Scenario: Legacy persisted record resolves comp from composition
- **WHEN** a persisted crew record contains only `"composition": "spec-ops"`
- **THEN** the response includes `"comp": "spec-ops"` and `"composition": "spec-ops"`

#### Scenario: Mismatched persisted fields normalize to comp
- **WHEN** a persisted crew record contains `"comp": "spec-ops"` and `"composition": "worker"`
- **THEN** the mismatch is logged and the response includes both fields as `"spec-ops"`
