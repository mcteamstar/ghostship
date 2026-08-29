# Migration assessment crew

A `migration-assess` ghostship runs an AWS migration assessment against one
[Migration Pathfinder](https://github.com/Versent/migration-pathfinder) project,
reached over Pathfinder's MCP server. Where `spec-ops` drives an OpenSpec change
through explore → propose → apply → archive, this loadout drives an *estate*
through discovery → attribution → disposition → sequencing → business case.

**Status: working end to end against a live Pathfinder project.** Verified on
Podman 6.1 / macOS: a crew launches with its full roster, registers the
Pathfinder MCP server, and personas read real project data through the
transport proxy.

## Why Pathfinder is the system of record

Pathfinder already holds the VMware inventory, the software and licence estate,
the workloads, their migration treatment, the wave plan and the business case.
It also already has the propose/confirm mechanism the in-app AI advisor uses.

So this crew does not build a parallel assessment and file it at the end. It
works *inside* Pathfinder: every finding becomes a change proposal a human
operator confirms in the app, and the assessment's completion state is queried
back out of Pathfinder rather than tracked in a checklist.

Two consequences shape everything else:

- **Nothing the crew proposes is real until a human confirms it.** Every write
  tool creates a pending `AiChangeProposal`. There is deliberately no confirm
  tool on the MCP surface and there should never be one. A persona reporting
  success has filed for review, not changed the assessment.
- **One crew is one engagement.** A Pathfinder MCP connection is permanently
  bound to a single project (`/mcp/{projectId}`) with no project argument on any
  tool. A second project means a second crew.

## The coverage model

The assessment has no `tasks.md`. Its definition of done is **ten gates, each
one a query against Pathfinder** — see
[`academy/skills/pathfinder-assessment/SKILL.md`](../academy/skills/pathfinder-assessment/SKILL.md)
for the full detail. A checklist drifts from reality silently; a query cannot.

| # | Gate | Owner |
|---|------|-------|
| 1 | Every VM is attributed to a workload | Chronicle |
| 2 | Every workload carries real context (description, criticality, category) | Chronicle |
| 3 | Compute sizing inputs are trustworthy | Sounder |
| 4 | Storage is attributed and sized | Ballast |
| 5 | Licence position is certain (no unresolved `needsReview`) | Ledger |
| 6 | OS lifecycle risk is stated | Ledger |
| 7 | Every workload has a reasoned, reviewed disposition | Compass |
| 8 | Every surviving workload is sequenced into a wave | Tide |
| 9 | The commercials are complete | Purser |
| 10 | The review queue is clean | Steward |

Gates 1 and 2 are upstream of everything: treatment, sequencing and cost are all
per-workload, so an unattributed VM is invisible to every later gate. An
assessment reporting 90% treatment coverage while a fifth of the estate belongs
to no workload is reporting a number that means nothing, and both Steward and
the orders template are written to say so rather than round up.

## Personas

Nine assessment personas, plus Raven reused from the shared Academy pool for
coordination. Each maps to a distinct cluster of the Pathfinder tool surface.

| Agent | Role | Gate | Writes to Pathfinder |
|:------|:-----|:-----|:---------------------|
| **Chronicle** | Application context — turns raw VM inventory into workloads with business meaning, mining discovery material, transcripts and questionnaires | 1, 2 | `workloads_create`, `workloads_update`, `workload_notes_create` |
| **Sounder** | Compute estate — VM and host sizing, allocated versus used, power state, clustering, templates and the hypervisor layer | 3 | read only |
| **Ballast** | Storage — datastore capacity reconciliation, thin-provisioning exposure, tiering, and the data volumes that constrain a cutover window | 4 | read only |
| **Ledger** | Licensing and entitlement — resolves `licenceClassification` uncertainty, BYOL versus license-included, Dedicated Host constraints, end-of-support exposure | 5, 6 | `virtual_machines_propose_licence_override`, `workload_notes_create` |
| **Compass** | Disposition — the 7Rs call per workload, with a reason and a note a stakeholder could argue with | 7 | `workloads_propose_treatment` |
| **Tide** | Sequencing — waves that are dependency-safe, capacity-feasible and retire risk early | 8 | `waves_create`, `workloads_propose_wave_assignment` |
| **Purser** | Commercials — target run cost, on-premises baseline, rightsizing, licensing impact, break-even and NPV | 9 | `workloads_propose_calculator_link` |
| **Steward** | Governance — audits all ten gates from live queries, keeps the review queue clean, reports honest completion state | 10 | `change_proposals_reject` only |
| **Cartographer** | Author — writes the delivered assessment document from Pathfinder's data and the crew's findings | — | none |
| **Raven** | Coordination — the recurring check-in that dispatches the persona owning the most-blocking open gate | — | none |

Raven has no Pathfinder access by design. It reads `assessment/coverage.md` —
Steward's output — as its view of state, and dispatches Steward to refresh it.
That keeps exactly one persona computing coverage, so the loop cannot act on two
disagreeing views of the same estate.

### Enforcement, honestly

As with `spec-ops` (see [agents.md](agents.md#steering-not-enforcement)), the
`tools`/`allowedTools` arrays are a real gate that KiroCrew enforces; the gate
ownership above is not. Two specific caveats for this loadout:

- **Every persona must opt in to the crew's MCP config explicitly.** KiroCrew
  agents do **not** inherit the crew's global `mcp.json`: each agent carries its
  own MCP server list, and one that neither sets `includeMcpJson` nor declares
  `mcpServers` of its own sees zero Pathfinder tools even when the crew is
  correctly wired. That failure is quiet and misleading — `launch` reports
  `mcp_servers: ["pathfinder"]`, `kiro-cli mcp list` shows the server registered
  under the `default` agent, and only the dispatched persona reports "a tool with
  the name 'project_get' does not exist".

  Each assessment persona therefore sets `"includeMcpJson": true` and carries
  `"@pathfinder"` in `tools` and `allowedTools`. Raven deliberately does not: it
  is coordination-only and reads Steward's coverage report rather than forming
  its own view of the estate.

- **Per-agent scoping is real, and the read-only split is not using it yet.**
  Because grants are per agent, `allowedTools` can name individual tools
  (`@pathfinder/virtual_machines_list`) rather than the whole server. That would
  turn the read-only versus proposing division in the table above into an
  enforced boundary instead of a prompt-level one — worth doing, but note the
  crew sets `dangerously_skip_permissions`, so how much `allowedTools` actually
  gates needs checking before relying on it.

- **Pathfinder's own role model is per-connection, not per-persona**, so all
  personas in a crew share one project role regardless of the above.

## Using it

```
launch(crew_id="acme-migration", composition="migration-assess")
supply(crew_id="acme-migration", path="discovery")     # workshop notes, questionnaires, CMDB extracts
captain(crew_id="acme-migration", action="order", template="assessment", interval=60)
```

Then let it run, and confirm proposals in the Pathfinder app as they arrive in
**Governance → AI Requests**. The crew's throughput is bounded by that review
queue, not by dispatch: the orders template explicitly holds and escalates to the
Admiral rather than piling more proposals onto an unreviewed backlog.

`pickup(crew_id="acme-migration")` shows task and mail state.
`evac(crew_id="acme-migration", path="assessment")` pulls out the working
findings and Cartographer's document.

Discovery material matters more here than in a `spec-ops` crew. Chronicle's
translation of unstructured material — workshop transcripts, application-owner
interviews, questionnaires — into structured workloads is the highest-value
thing this crew does, and the thing a human operator finds most tedious by hand.
A crew launched with no supplied context can only infer workloads from VM naming
and installed software, which is a much weaker assessment.

## How the Pathfinder connection works

Pathfinder's MCP server validates Cognito access tokens obtained through a
browser OAuth callback:

```
claude mcp add --transport http --client-id <id> --callback-port 8080 \
  pathfinder-<project> https://pathfinder.staging.sca.versent.io/mcp/<project>
```

A headless crew container cannot complete that callback, and access tokens last
about 15 minutes against a 7-day refresh token, so a long-running crew needs
refresh rather than a one-off injection. **Transport holds the credential and
proxies for the crew:**

```
crew (kiro-cli)                transport                     Pathfinder
  │                                │                              │
  │ POST /pathfinder/<crew>/mcp    │                              │
  │ Authorization: Bearer <crew    │                              │
  │   token, minted at launch>     │                              │
  ├───────────────────────────────►│                              │
  │                                │ validate against this crew's │
  │                                │ registry entry, then swap in │
  │                                │ a fresh Cognito token        │
  │                                │ POST /mcp/<project-id>       │
  │                                │ Authorization: Bearer <real> │
  │                                ├─────────────────────────────►│
  │◄───────────────────────────────┤◄─────────────────────────────┤
  │        response streamed back (SSE passes straight through)    │
```

A Pathfinder credential never enters a crew container, which is the same posture
as `admiral_secret` and `ga-kiro-auth`. Each crew authenticates with its own
token, minted at launch and destroyed by `nuke`, so a leaked crew token reaches
exactly one project and is revoked by nuking that crew. Transport refreshes the
Cognito token centrally for the whole fleet, and the crew's own `Authorization`
header is stripped before the upstream request so a crew cannot influence the
credential used on its behalf.

Configure it on the transport (see `config/ghostship.conf.example`):

| Setting | Purpose |
|:--------|:--------|
| `GA_PATHFINDER_URL` | Pathfinder origin, e.g. `https://pathfinder.staging.sca.versent.io` |
| `GA_PATHFINDER_TOKEN_URL` | Cognito token endpoint, for the refresh grant |
| `GA_PATHFINDER_CLIENT_ID` | Cognito app client id for the refresh grant |
| `GA_PATHFINDER_ACCESS_TOKEN` | A static access token. Expires in ~15 minutes, so this is for a bounded test run only |

`scripts/pathfinder-login.py` runs the browser OAuth flow once and writes the
refresh token to `<DATA_DIR>/ga-pathfinder-refresh` at mode 600 without printing
it:

```bash
python3 scripts/pathfinder-login.py \
  --origin https://pathfinder.staging.sca.versent.io \
  --client-id <cognito app client id>
```

Cognito's `PreSignUp` trigger rejects the first federated sign-in with
"Account linked. Please sign in again." while it links the identity. That is
expected once per operator; run the command again and it completes.

For unattended use, write the refresh token to
`<DATA_DIR>/ga-pathfinder-refresh` (mode 600) and set the token URL and client
id. Transport caches the access token and refreshes it 90 seconds before expiry.

A crew launched without `pathfinder_project`, or a transport with no credential
configured, still comes up — Pathfinder calls return 503 with a message saying
which piece is missing, rather than the crew failing to launch.

## Test run

Podman is required and is not installed on every machine; check with
`podman --version` first (`brew install podman podman-compose` on macOS, then
`podman machine init && podman machine start`).

```bash
# 1. Build the new crew image and recreate transport with Pathfinder config.
#    Get a fresh access token from a browser session for this first run.
GA_PATHFINDER_URL="https://pathfinder.staging.sca.versent.io" \
GA_PATHFINDER_ACCESS_TOKEN="<token>" \
  ./install.sh

# 2. Launch a crew bound to one Pathfinder project.
#    launch(crew_id="acme-migration", composition="migration-assess",
#           pathfinder_project="74f603e9-f784-4147-8ef2-53b1118372b6")

# 3. Confirm the roster and the MCP registration came back on the launch result:
#    "personas": [...], "mcp_servers": ["pathfinder"]

# 4. Smallest useful first dispatch — Steward reads all ten gates and writes
#    assessment/coverage.md. It touches every read tool the other personas use,
#    so it fails fast and informatively if the connection is wrong:
#    dispatch(crew_id="acme-migration", agent="steward",
#             task="Audit all ten coverage gates against Pathfinder and write
#                   assessment/coverage.md. Report each gate's count.")

# 5. pickup(crew_id="acme-migration") to watch it, then:
#    evac(crew_id="acme-migration", path="assessment")
```

Only once that round trip works is it worth starting the recurring loop with
`captain(..., template="assessment", interval=60)`. Move to the refresh-token
configuration before leaving a crew running unattended — a static access token
will expire mid-assessment and every Pathfinder call starts returning 503.

**If a persona reports that a Pathfinder tool "does not exist"**, the crew is
wired but that agent has not opted in — check `includeMcpJson` and the
`@pathfinder` grant in its JSON, and confirm with `kiro-cli mcp list` inside the
crew, which lists servers per agent.

**What to check if step 4 fails.** `podman logs ga-transport` shows the proxy's
own errors, which are deliberately specific: a 401 means the crew's token did
not match its registry entry, a 503 names the missing piece (project binding,
`GA_PATHFINDER_URL`, or credential), and a 502 means Pathfinder itself was
unreachable. Inside the crew, `kiro-cli mcp list` shows whether the server
registered; transport logs say whether it went through the CLI or fell back to
writing `~/.kiro/settings/mcp.json` directly.

## What changed in transport

Three things were hardcoded to the `spec-ops` loadout and had to become
composition-aware. All three are covered by
`tests/unit/test_migration_assess.py`.

**Persona rosters are now manifest-driven.** `PERSONA_NAMES` was a fixed tuple
gating `dispatch` and `schedule`, so `dispatch(agent="chronicle")` was rejected
outright. Rosters now come from the crew type's manifest `agents` selection,
which already declared them, and are recorded in the registry at launch so a
manifest edited later cannot invalidate a running crew. The same roster drives
mailbox reads, the Raven check-in prompt's dispatch list, and the crew's default
agent. Crews registered before this change fall back to the shared Academy
roster, and `crews` now reports each crew's roster so a caller can see which
agent names `dispatch` will accept.

**Crews can be given MCP clients.** `_copy_mcp_config` reads
`crews/<type>/mcp.json`, substitutes `{{TRANSPORT_URL}}`, `{{CREW_ID}}` and
`{{CREW_MCP_TOKEN}}`, and registers the servers with
`kiro-cli mcp add --scope global`, falling back to writing
`~/.kiro/settings/mcp.json` if the CLI rejects the call. Global scope is
essential: every dispatched task runs in its own `subagent_*/` directory, so a
workspace-scoped server would be invisible to all of them. A crew type with no
`mcp.json` (spec-ops) is unaffected.

**The OpenSpec store is only seeded where it is used.** `_seed_openspec_store`
ran unconditionally. It now runs only for crew types whose manifest selects at
least one `openspec-*` skill, so a migration-assess crew does not get an unused
store at its workspace root.

Also: `crews/_base/admission/Containerfile` still hardcodes the spec-ops
mailboxes, so this crew type provisions its own in its own image layer. Folding
that into the base image as a build arg is the tidier end state.

## Known rough edges

- **Steering duplication.** `ASSESSMENT_ORDERS.md` restates the generic crew
  environment facts (working-directory isolation, mail conventions, unbounded
  loops, duplicate dispatch) from `STANDING_ORDERS.md`, because that file also
  carries `spec-ops`-specific content — the shared OpenSpec store and the
  five-worker roster — that would be actively wrong in this crew. The cleaner
  fix is to split the generic core into its own steering doc both crew types
  select. That touches `spec-ops`, so it was left alone here.
- **Verified as a connection, not yet as an assessment.** A crew reads real
  project data through the proxy, but no crew has yet worked a coverage gate to
  completion or produced an assessment document.
- **`kiro-cli mcp add` cannot set auth headers** in the version shipped in the
  crew image (there is no `--headers` flag), so the CLI path in
  `_copy_mcp_config` always fails for an authenticated HTTP server and the
  direct file write is what actually runs. The CLI attempt is kept because it
  is the version-proof path if the flag lands.
- **`KIRO_LICENSE=pro` is required for an Identity Center login.** Left empty,
  kiro-cli's interactive menu silently defaults to the free-tier Builder ID and
  `KIRO_IDENTITY_PROVIDER` is never used.
- **Nine personas is a lot.** Ballast is the thinnest gate (Pathfinder exposes
  only `storage_list`/`storage_get` for it) and is the obvious candidate to fold
  into Sounder if dispatch overhead outweighs the separation in practice.
- **Everything this crew produces is a first draft for qualified Versent
  review.** Both the steering doc and Cartographer's prompt say so explicitly,
  and Cartographer is instructed to state it at the top of the assessment
  document.
