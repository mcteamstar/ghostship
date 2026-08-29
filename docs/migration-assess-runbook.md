# Migration assessment runbook

How to stand up a `migration-assess` ghostship, run an assessment against a
Migration Pathfinder project, watch it work, and get the artefacts back out.

For what the loadout is and why it is built this way, see
[migration-assess.md](migration-assess.md). This document is the operational
sequence only.

Everything below has been run end to end on Podman 6.1 / macOS against a live
Pathfinder staging project, except where marked **not yet verified**.

---

## 1. One-time setup

### Prerequisites

- **Podman >= 4.4** and **podman-compose**. On macOS:
  `brew install podman podman-compose`.
- A kiro-cli identity. For a Versent org licence this is Identity Center, not
  the free-tier Builder ID.
- Access to a Migration Pathfinder project, and its project UUID.

**macOS: only one Podman VM can run at a time.** Ghostship creates its own
(`ghost-academy`) by default, so stop any other machine first:

```bash
podman machine stop podman-machine-default
```

### Write a config file

`install.sh` does **not** auto-discover config the way `start.sh` does, so you
must pass `--config` every time or it will prompt for an identity provider.
Copy the example and fill it in:

```bash
cp config/ghostship.conf.example config/ghostship.conf
```

The settings that matter:

```bash
# Identity Center, not Builder ID. Without KIRO_LICENSE=pro, kiro-cli's
# interactive login menu silently defaults to the free tier and
# KIRO_IDENTITY_PROVIDER is never used.
KIRO_IDENTITY_PROVIDER="https://<your-idc>.awsapps.com/start/#/"
KIRO_REGION="ap-southeast-2"
KIRO_LICENSE="pro"

# Trim these if your disk is tight. Defaults are 8 CPU / 16 GiB / 100 GiB.
GA_MACHINE_CPUS=6
GA_MACHINE_MEMORY=12288
GA_MACHINE_DISK=40

# Pathfinder MCP proxy — transport holds the credential, not the crew.
GA_PATHFINDER_URL="https://pathfinder.staging.sca.versent.io"
GA_PATHFINDER_TOKEN_URL="https://<cognito-domain>/oauth2/token"
GA_PATHFINDER_CLIENT_ID="<cognito app client id>"
```

`config/*.conf` is gitignored.

### Install

```bash
./install.sh --config config/ghostship.conf
```

Builds five images (about 6 GB in the VM) and starts `ga-transport` on
`localhost:64057`. Verify:

```bash
curl -s http://localhost:64057/health     # -> ok
curl -s http://localhost:64057/version    # -> {"transport":"0.1.2"}
```

### Get a Pathfinder refresh token

```bash
python3 scripts/pathfinder-login.py \
  --origin https://pathfinder.staging.sca.versent.io \
  --client-id <cognito app client id>
```

Opens a browser, catches the loopback redirect, and writes the refresh token to
`<DATA_DIR>/ga-pathfinder-refresh` at mode 600 without printing it. Copy the
`GA_PATHFINDER_*` values it prints into your config and re-run `install.sh`.

Cognito's `PreSignUp` trigger rejects the **first** federated sign-in with
"Account linked. Please sign in again." while it links the identity. Run the
command again and it completes.

### Connect a client

```bash
claude mcp add --transport http ghostship http://localhost:64057/mcp --scope user
```

Restart Claude Code. `claude mcp list` should show `ghostship ✔ Connected`. For
kiro-cli:

```bash
kiro-cli mcp add --name ghostship --url http://localhost:64057/mcp --scope global
```

---

## 2. Launch a crew for an engagement

One crew is one engagement. A Pathfinder MCP connection is bound to a single
project permanently, so a second project needs a second crew.

```
launch(crew_id="acme-migration",
       composition="migration-assess",
       pathfinder_project="<project-uuid>")
```

The **first** launch on a fresh install returns a device-auth URL instead:

```json
{"error": "not_authenticated",
 "login_url": "https://<idc>.awsapps.com/start/#/device?user_code=XXXX-XXXX"}
```

Approve it in a browser, then call `launch` again.

> **Do not run `install.sh` while a login is pending.** Restarting transport
> sweeps the login container, discarding an approval you have already given, and
> you will need a fresh code.

A good launch returns:

```json
{"status": "ready",
 "personas": ["sounder","ballast","ledger","chronicle","compass","tide",
              "purser","steward","cartographer","raven"],
 "mcp_servers": ["pathfinder"],
 "pathfinder_project": "<project-uuid>"}
```

Check all three fields. `mcp_servers` missing means the crew cannot reach
Pathfinder; no `pathfinder_project` means every Pathfinder call will 503.

### Supply discovery material

Chronicle's translation of unstructured material into structured workloads is
the highest-value thing this crew does, and it cannot do it from VM names alone.
Deliver workshop transcripts, questionnaires and CMDB extracts before starting:

```
supply(crew_id="acme-migration", path="discovery")
```

then POST the file bytes to the returned URL. They land at the workspace root.

---

## 3. Initiate the assessment

### Recommended: one gate per dispatch

**This is measured, not stylistic.** One task asked to audit all ten coverage
gates over a 1,284-VM estate ran 37 minutes, wrote nothing, and drifted off
task. The same crew asked for one gate returned a quantified, correctly-hedged
answer in under two minutes.

Every gate task should state three things: the single gate it covers, where to
write its findings, and a bound.

```
dispatch(crew_id="acme-migration", agent="ledger",
         task="Coverage gate 5 ONLY (licence certainty). Do not audit other "
              "gates. Report how many VMs need licence review out of the estate "
              "total, and the dominant operating systems (label as a sample if "
              "not reconciled). Write your findings to "
              "../assessment/gate-5-licensing.md (workspace root, one level "
              "ABOVE your subagent_ directory) using mkdir -p ../assessment "
              "first. Confirm the file path. Max 15 tool calls.")
```

The `../assessment/` path matters. Every task runs in its own
`subagent_<task_id>/` directory, and a file written inside it is invisible to
every other task and to Cartographer.

Gate ownership, in dependency order:

| Order | Gate | Persona |
|---|---|---|
| 1 | Every VM attributed to a workload | `chronicle` |
| 2 | Every workload has real context | `chronicle` |
| 3 | Compute sizing trustworthy | `sounder` |
| 4 | Storage attributed and sized | `ballast` |
| 5 | Licence position certain | `ledger` |
| 6 | OS lifecycle risk stated | `ledger` |
| 7 | Disposition set and reasoned | `compass` |
| 8 | Surviving workloads sequenced | `tide` |
| 9 | Commercials complete | `purser` |
| 10 | Review queue clean | `steward` |

Gates 1 and 2 gate everything downstream. Do not start gate 7 or later while
gate 1 has a material gap; treatment, sequencing and cost are all per workload,
so an unattributed VM is invisible to every later gate.

Gates 3, 4, 5 and 6 read inventory rather than workloads, so they can run
concurrently with gate 1. Two concurrent dispatches work fine.

The final artefact comes last:

```
dispatch(crew_id="acme-migration", agent="cartographer",
         task="Write assessment/migration-assessment.md from Pathfinder and the "
              "gate findings in assessment/. State the coverage gaps explicitly.")
```

### Autonomous: the Captain loop — **not yet verified**

```
captain(crew_id="acme-migration", action="order",
        template="assessment", interval=60)
```

Appends a standing order to the crew's `captain@localhost` mailbox and starts a
recurring Raven check-in that dispatches whichever persona owns the most-blocking
open gate. `captain(..., action="status")` reports its state; `action="stop"`
pauses it.

This path has **not been run end to end**. The orders template is written and
carries the one-gate-per-dispatch rule, but the manual dispatch sequence above is
what has actually been exercised. Use the loop knowing that.

---

## 4. View progress

### From your MCP client

```
pickup(crew_id="acme-migration")                          # all tasks + mail summary
pickup(crew_id="acme-migration", task_id="9d836fd0")      # one task
pickup(crew_id="acme-migration", task_id="...", timeout_secs=30)   # poll
crews()                                                   # fleet, rosters, status
```

`pickup` includes mail counts, and when polling it returns early with
`reason: "admiral_mail"` if a persona escalates.

### From the shell

```bash
curl -s http://localhost:64057/crews/acme-migration/api/spawn   # tasks
curl -s http://localhost:64057/crews/acme-migration/api/crons   # schedules
```

### Crew web UI

```
http://localhost:64057/crews/acme-migration/ui
```

Two things to know:

- **There are no live updates.** Transport proxies HTTP but not websockets, so
  the page will not refresh itself. Reload manually.
- **"Sessions" means interactive chat sessions, not dispatched tasks.** A
  dispatched task will not appear there. Look for the Agents or Tasks view.

If the page is blank or shows a stale setup screen, unregister the service
worker (DevTools, Application, Service Workers, Unregister) and hard-reload.

### Transport logs

```bash
podman --connection ghost-academy logs ga-transport | tail -50
```

Pathfinder proxy traffic appears as `POST /pathfinder/<crew>/mcp`. Status codes
are deliberately specific: 401 means the crew token did not match, 503 names the
missing piece (project binding, `GA_PATHFINDER_URL`, or credential), 502 means
Pathfinder itself was unreachable.

---

## 5. Retrieve artefacts

`evac` handles **files, not directories.** A directory path fails with
"Podman archive member is not a regular file".

### A single artefact

```
evac(crew_id="acme-migration", path="assessment/gate-5-licensing.md")
```

Returns a presigned URL valid for 300 seconds. Download it and you have the raw
file:

```bash
curl -o gate-5-licensing.md "<url>"
```

### The whole assessment folder

Tar it inside the crew first, then evac the tarball:

```
dispatch(crew_id="acme-migration", agent="cartographer",
         task="Mechanical task, no Pathfinder calls. Run exactly: "
              "cd .. && tar -czf assessment.tgz assessment/ && ls -la assessment.tgz. "
              "Report the byte size. Nothing else.")

evac(crew_id="acme-migration", path="assessment.tgz")
```

```bash
curl -o assessment.tgz "<url>" && tar xzf assessment.tgz
```

Pathfinder itself remains the system of record for the structured data —
workloads, treatments, waves, the business case. The files you evac are the
crew's working findings and the written assessment, not a substitute for it.
Pending change proposals are confirmed in the Pathfinder app under
**Governance → AI Requests**, never by the crew.

---

## 6. Between sessions, and tear down

Crew containers idle-stop after 300 seconds and restart transparently on the
next call, so leaving a crew alone is fine and costs nothing.

**A persona's result is only durable if it wrote a file.** Both volumes survive
an idle-stop, so `assessment/`, every `subagent_*/` directory and the crew's MCP
registration all persist. The crew gateway's task list does not: it is in-memory,
so after an idle-stop `pickup(task_id=...)` can no longer reach a task from
before the stop, and the UI's task view comes back empty. This is the practical
reason every gate task must write to `assessment/<gate>.md` rather than only
returning its findings in the task result.

```bash
./start.sh --config config/ghostship.conf   # after a reboot
```

```
nuke(crew_id="acme-migration", confirm=True)
```

`nuke` destroys the container and **both volumes**, so evac anything you want
first. It also revokes that crew's Pathfinder proxy token.

---

## 7. Known limitations

- **The Captain autonomous loop is unverified.** See section 3.
- **No live UI updates.** Websockets are not proxied.
- **Pathfinder list filters are ignored, and paginating with a non-unique
  `sort` silently drops records.** Both are confirmed defects in Pathfinder
  (see `Versent/migration-pathfinder#321` for the pagination one). The
  `pathfinder-assessment` skill instructs personas to omit `sort`, reconcile
  distinct counts against `meta.total`, and label unreconciled figures as
  samples. Until the filters are fixed, gates that would naturally use a
  server-side filter must aggregate client side, which makes them much slower.
- **A gate can still outrun a single task.** Gate 3 on a 1,284-VM estate was
  still running after 14 minutes, because with filters broken it had to
  aggregate the whole estate by hand. Where that happens, split the gate by a
  filter you apply yourself (one OS family, one cluster) and say in the task
  description which slice it covers.
- **Everything the crew produces is a first draft for qualified Versent review.**
  Do not put a machine-generated recommendation in front of a client as a
  signed-off position.
