## Context

See proposal.md for motivation. The demo needs to show the full ghostship loop in ~6 seconds of watchable content using only tools already in the project (kiro-cli as Admiral, asciinema for recording, agg for gif conversion).

## Goals / Non-Goals

**Goals:**
- A single gif that communicates the value proposition without any caption explanation
- Embeddable in README.md and shareable on social media
- Recorded from a real session (no scripted/faked output)

**Non-Goals:**
- Showing internal agent working (tool calls, intermediate output)
- Covering every ghostship feature
- A video with narration or music

## Decisions

**Recording tool: asciinema + agg**
kiro-cli is a terminal app — asciinema captures real session output with accurate timing. agg converts to gif. Both are installed. VHS was considered but requires pre-scripted `Sleep` timings which would either fake the agent response time or require tight coupling to academy's current performance.

**Script: four beats**
```
1. ls openspec/changes/              — show real pending work
2. Natural language prompt to Kiro   — "launch a crew, drive change X with SDD"
3. [fast-forward] crew working       — agg --speed compresses the wait
4. "evac the changes and make a PR"  — result: a real PR
```
This arc (delegate → wait → result) is the whole pitch. The viewer doesn't need to understand the middle.

**Change to drive: trn-163-demo-gif itself**
Meta, readable, and self-contained — the crew drives the very change being demoed. Requires only docs edits so the cycle is fast and predictable (no test suite to run, no complex implementation).

**Fast-forward approach: `agg --speed N`**
Apply uniform speed-up to the whole cast after trimming leading/trailing dead time with `asciinema-edit`. Target output duration: 30–60 seconds at 3–5× speed gives ~6–20 seconds of gif. Adjust speed multiplier after first render.

**Output location: `docs/images/ghostship-demo.gif`**
Consistent with existing image assets in that directory.

## Risks / Trade-offs

- [Real session variability] The SDD cycle time is non-deterministic → Mitigation: drive a simple docs-only change (this one) so Spectre/Ghost work is minimal and predictable; re-record if a run is unusually slow
- [Gif file size] Long recordings at high quality produce large gifs → Mitigation: `agg --speed` reduces frame count; target < 5 MB for README embedding
- [Terminal appearance] Default terminal theme may not look polished → Mitigation: `agg` supports `--theme` flag; use a clean dark theme (e.g. `monokai`)
