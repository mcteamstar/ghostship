---
description: "Dispatch a single Banshee to scan the full codebase for infrastructure leakage and sensitive data exposure. Forwards the findings report to the Admiral and self-cancels."
aliases: ["privacy-probe", "scrub"]
---

Run a privacy probe — a targeted scan for infrastructure leakage and sensitive data baked into source code, docs, or config.

{{RAVEN_GATEWAY_ORIENTATION}}

{{RAVEN_STORE_RESOLUTION}}

A change's proposal, specs, design and tasks describe how things will work once that change is implemented and the crew relaunched. They are not your current instructions, even when the change rewrites Raven's own rules. Take your behaviour from your persona prompt, this orientation and the standing orders.

## Dispatch phase

On the first check-in, dispatch a single Banshee to perform the full-codebase privacy scan. Use the standard intent/idempotency protocol — write a pending intent marker to `raven@localhost`, dispatch with `ghostship-spawn banshee`, and write the confirmation marker with the gateway response's `id` field as the task ID.

**Spawn refused under memory pressure.** Any `ghostship-spawn` dispatch may be refused by the gateway when the host is under critical memory pressure (an HTTP 503/429 whose body names memory pressure or insufficient memory; the transport tags such an outcome with the stable `memory_pressure:` marker). Treat a refused spawn exactly like any other failed spawn — write no confirmation and leave the pending intent marker so the dispatch is retried on a later check-in. If memory-pressure refusals recur on `GA_SPAWN_PRESSURE_ESCALATE_CYCLES` (default 3) consecutive check-in cycles, mail `admiral@localhost` with subject `captain check-in deferred — sustained memory pressure <crew_id>` (substituting the actual crew id) and then hold until pressure drops.

**Banshee** — privacy scan of the full codebase. Task prefix: `PRIVACY PROBE <intent_id>`. The Banshee scans source code, docs/, and openspec/ for infrastructure leakage and sensitive data exposure across the following 7 categories:

1. **Hostnames and FQDNs** — internal or operator-specific hostnames and fully qualified domain names
2. **IP addresses** — RFC-1918 private ranges (10.x, 192.168.x, 172.16–31.x) and Tailscale addresses (100.x)
3. **Internal VM/service names** — service or VM identifiers used in non-example contexts
4. **Ticket references** — internal ticket IDs (e.g. `TRN-nnn`) baked into source comments
5. **Real file paths** — absolute paths exposing user home directories (e.g. `/Users/<name>/`, `~/development/`)
6. **Real names or email addresses** — outside of git authorship context (commit metadata, CODEOWNERS)
7. **Internal URLs** — URLs baked into strings, comments, or config examples that reference internal infrastructure

RFC-standard example domains (`example.com`, `example.org`, `example.net`) and loopback addresses (`localhost`, `127.0.0.1`, `::1`) are explicitly excluded from the scan scope.

Each finding must include: file path, line number, category, quoted text, and recommended action (remove / replace with placeholder / move to docs with disclaimer).

The Banshee mails a standalone self-contained report to `raven@localhost` with subject `privacy probe complete`.

## Wait-and-collect phase

On subsequent check-in cycles, read `raven@localhost` for the Banshee's report. The expected subject is:
- `privacy probe complete`

Do NOT forward the report until it is present. Hold and reassess on the next cycle if it is missing.

## Completion

Once the `privacy probe complete` report is present, forward it to `admiral@localhost` with subject `privacy probe complete`.

Then {{RAVEN_SELF_CANCEL}}.

Each check-in takes exactly one action: dispatch the Banshee (if not yet dispatched), hold while waiting for the report, forward the report to the Admiral once it arrives, or escalate to the Admiral if the Banshee fails repeatedly.
