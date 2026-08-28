---
name: pathfinder-assessment
description: How to read, assess and update a Migration Pathfinder project over its MCP server. Use whenever a task involves discovery, workload composition, migration treatment, wave planning, licensing or the business case for a Pathfinder project — it carries the coverage model that defines when an assessment is complete, the enum values writes must use, and the propose/confirm etiquette every write goes through.
allowed-tools: Bash(python3:*), Bash(cat:*), Bash(ls:*), Bash(grep:*), Bash(mkdir:*), Bash(tee:*)
metadata:
  author: ghostship
  version: "1.0"
---

# Pathfinder assessment

Migration Pathfinder is the system of record for this assessment. It holds the
VMware inventory (hosts, VMs, datastores), the software and licence estate, the
workloads assembled from that inventory, their migration treatment, wave
assignment, and the resulting business case.

This crew reaches it over MCP, as the `pathfinder` server. **The connection is
permanently bound to one project.** There is no project argument on any tool and
no ambient "current project" that can drift — if you are talking to Pathfinder at
all, you are talking to this engagement's project.

## The two rules that matter most

**1. You never write to Pathfinder directly.** Every write tool creates a
*pending change proposal*. A human operator confirms it in the app. Nothing you
propose is real until they do. Treat a successful write call as "filed for
review", not "done" — and never report an assessment finding as applied because
you proposed it.

**2. Read before you propose.** Every proposal costs an operator a review. A
proposal that restates what is already there, or that fails validation at confirm
time, is worse than no proposal. Fetch the entity first, check the field you
intend to change actually needs changing, and cite what you read in the
`rationale`.

## Coverage model — when is the assessment done?

Do not keep a private checklist of what you have covered. **The assessment's state
lives in Pathfinder, and you derive it by querying.** A checklist drifts; a query
cannot. Each gate below is a question you answer with read tools, and the
assessment is complete when every gate returns an empty gap set.

| # | Gate | How to test it | Owner |
|---|------|----------------|-------|
| 1 | Every VM is attributed to a workload | Union the `virtualMachineIds` of every `workloads_list` entry; diff against `virtual_machines_list`. The remainder is the gap. | Chronicle |
| 2 | Every workload carries real context | `workloads_list` — flag any with an empty `description`, or `category` = `unknown-needs-review`. | Chronicle |
| 3 | Compute sizing inputs are trustworthy | `virtual_machines_list` — flag VMs with absent or implausible `vCpuCount` / `allocatedRamGb` / `provisionedDiskGb`, and reconcile against `hosts_list` cluster capacity. | Sounder |
| 4 | Storage is attributed and sized | `storage_list` — every datastore reconciled to hosts, and its consumption traced through to workloads. Flag orphaned or unattributed capacity. | Ballast |
| 5 | Licence position is certain | `virtual_machines_get` — flag every VM whose `licenceClassification.needsReview` is true and which has no `licenceOverrideOperatingSystem` set. | Ledger |
| 6 | OS lifecycle risk is stated | `os_lifecycle_list` — every distinct OS in the estate is matched, and every workload on a past-end-of-support OS carries a note saying what happens to it. | Ledger |
| 7 | Every workload has a disposition | `workloads_list` — flag `migrationTreatment` = `Unassigned`, `treatmentReason` = `not-assessed`, an empty `treatmentReasonNote`, or `treatmentReviewed` = false. | Compass |
| 8 | Every surviving workload is sequenced | `workloads_list` — flag any workload with no `waveId` whose treatment is not `Retire`. | Tide |
| 9 | The commercials are complete | `business_cases_list` returns a case, `business_cases_executive_summary_get` is populated, and `migration_path_summary_get` maps every non-`Retire` workload. | Purser |
| 10 | The review queue is clean | `change_proposals_list` — no proposal left `awaiting_confirmation` beyond the agreed review window, and none of your own known-bad proposals left unrejected. | Steward |

Gates 1–2 gate everything downstream: treatment, sequencing and cost are all
per-workload, so an unattributed VM is invisible to every later gate. Do not
report progress on gates 7–9 while gate 1 has a material gap — say so instead.

## Enum values — these are not freeform

A value outside these sets passes proposal creation and then **fails at confirm
time with a raw database error**, landing in the operator's queue as a broken
proposal. This has happened in production. Use these exact strings.

`migrationTreatment`: `Retire` `Retain` `Rehost` `Replatform` `Refactor`
`Relocate` `Unassigned`

`treatmentReason`: `powered-off` `licence-obsolete` `default-rehost`
`not-assessed` `manual` `mixed-workload` `srm-placeholder` `vm-template`
`hypervisor-layer` `managed-service-candidate` `other`

`businessCriticality`: `critical` `high` `medium` `low`

`category`: `identity-security` `networking-services` `infrastructure-services`
`end-user-collaboration` `platform-operations-tooling` `data-integration`
`business-applications` `research-laboratory` `web-digital-experience`
`unknown-needs-review`

Prefer the specific `treatmentReason` over `other` — `hypervisor-layer` for the
vSphere/ESXi platform layer, `managed-service-candidate` where AWS delivers the
function natively, `vm-template` and `srm-placeholder` for non-running artefacts.
`other` with a good `treatmentReasonNote` beats a wrong specific value.

## Tool surface

**Read (all personas):** `project_get`, `virtual_machines_list|get`,
`hosts_list|get`, `software_list|get`, `licenses_list|get`, `workloads_list|get`,
`workload_notes_list|get`, `waves_list|get`, `storage_list|get`, `tags_list`,
`os_lifecycle_list`, `migration_path_summary_get`, `business_cases_list|get`,
`business_cases_executive_summary_get`, `cost_line_items_list`,
`vm_cost_summary_get`, `audit_log_list`, `change_proposals_list|get`.

List tools take `cursor`, `limit` (max 200), `sort`, `order`, and a `filters`
map. **Paginate properly** — a `limit` of 200 on a several-thousand-VM estate is
a sample, not the estate, and an assessment built on the first page is wrong in a
way that is very hard to see. Follow `nextCursor` to exhaustion, or filter
deliberately and say that you did.

### Pagination loses records on a non-unique sort. Always reconcile.

Measured against a 1,284-VM project, paging to exhaustion with `limit=200`:

| Sort | Rows fetched | Distinct | Missing |
|---|---:|---:|---:|
| `sort=id` | 1,290 | 1,284 | **0** |
| no `sort` | 1,290 | 1,284 | **0** |
| `sort=name` | 968 | 820 | **464 (36%)** |
| `sort=clusterOrResourcePool` | 748 | 630 | **654 (51%)** |

`name` is not unique in a real estate — 53 names were shared by more than one VM,
and `win2019std_template` alone appeared 12 times. Sorting on a non-unique column
makes the cursor skip and repeat rows, and `nextCursor` then goes null **early**.
There is no error. The loop simply ends, and you are left holding two thirds of
the estate believing it is all of it.

So:

- **Sort by `id`, or do not pass `sort` at all**, whenever you intend to page
  through everything. Sort in your own output if you need a different order.
- **Reconcile every sweep**: compare the count of distinct ids you collected
  against `meta.total`. If they differ, say so and treat the result as
  incomplete — never report a total you did not actually reconcile.
- **De-duplicate by id.** Even on `sort=id` there is about one repeated row per
  page boundary (1,290 rows fetched for 1,284 records), so a naive row count
  overstates the estate slightly and any client-side aggregate double-counts.

**Write (proposal-creating):** `workloads_create`, `workloads_update`,
`workloads_propose_treatment`, `workloads_propose_wave_assignment`,
`workloads_propose_calculator_link`, `workload_notes_create`,
`virtual_machines_propose_licence_override`, `waves_create`,
`change_proposals_reject`.

There is deliberately **no confirm tool.** Confirming is a human action, in the
app. Do not look for one, and do not ask the Admiral to have one added.

**Resources:** `pathfinder://projects/{id}/summary` for headline counts, and
`pathfinder://schemas/{virtual-machines,workloads,workload-notes}` for field and
filter definitions.

## Traps worth knowing before you hit them

- **`workloads_propose_treatment` is the right tool for treatment**, not
  `workloads_update`. It attributes the change as `treatmentSource: 'agent'`,
  which keeps agent recommendations distinguishable from operator decisions in
  every later report. Using the generic update path launders that distinction away.
- **`workloads_propose_calculator_link` will not displace an active estimate.**
  Check `activeCalculatorImport` on `workloads_get` first; if one is already
  active, a newly attached estimate does not become active and your proposal
  quietly achieves nothing.
- **`virtual_machines_propose_licence_override` is set-only.** There is no tool to
  clear a confirmed override. Read `licenceClassification` first and be sure —
  an operator has to undo a wrong one by hand in the app.
- **`waves_create` never takes a sequence.** Position is assigned at confirm time
  as the next available slot. There is no tool to reorder, rename or delete a
  wave, so propose waves in the order you want them and get it right first time.
- **`workloads_propose_wave_assignment` covers assign, move and unassign** — all
  three are the same tool; `waveId: null` unassigns.
- **One proposal, one entity.** Do not try to batch several different entities
  into a single proposal; the apply loop is not transactional and a partial
  failure leaves changes committed with no audit trail.

## Rejecting your own work

`change_proposals_reject` is the one write that resolves rather than creates. If
you realise a proposal you filed is wrong, reject it with a reason rather than
filing a second, contradictory one on top. Two live proposals disagreeing about
the same field is the worst thing you can hand an operator. Rejecting applies
nothing to live data and the full record stays in the audit history.

## Reporting back

End every task with what you **read**, what you **found**, what you **proposed**
(with proposal ids), and what remains **open** in your gate. Quantify the gate:
"gate 5: 214 of 1,140 VMs still need review, down from 380" is useful. "Made
good progress on licensing" is not.
