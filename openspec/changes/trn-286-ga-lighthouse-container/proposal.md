# TRN-286 — ga-lighthouse: Decouple Fleet UI into its Own Portside Container

## Problem

The Lighthouse SPA and `/api/crews` REST endpoint currently live inside `ga-transport` — the HTML is a 600+ line heredoc string in `server.py` and the fleet API is a route handler alongside MCP tools and crew lifecycle machinery.

Transport is meant to be a pure bridge between `ga-portside` (MCP/portal traffic) and `ga-starboard` (crew containers). UI concerns should not accumulate there. The heredoc approach is unmaintainable as Lighthouse grows.

Additionally, there are two distinct traffic classes that should have distinct paths:

- **MCP traffic**: `portal → transport` (MCP tools, crew lifecycle, file transfer)
- **UI traffic**: `portal → lighthouse → transport` (fleet observability, future dashboards)

These are currently conflated inside the transport process.

## Proposal

Extract Lighthouse into a dedicated `ga-lighthouse` microservice container on `ga-portside`. Lighthouse owns the browser-facing surface. Transport becomes a data source that Lighthouse calls internally — never directly reachable from the browser for UI traffic.

```
MCP clients  →  ga-portal  →  ga-transport          (MCP + lifecycle)
Browser      →  ga-portal  →  ga-lighthouse          (SPA)
                                   ↓ portside
                              ga-transport            (fleet data API)
```

Per-crew KC dashboard traffic is unchanged — it goes `portal → transport → crew` because transport must inject the crew session cookie. That is a direct session proxy, not fleet observability, and belongs on transport.

## Design decisions

**D1 — Lighthouse is a microservice, not just static files**
Lighthouse needs a server-side component to call `ga-transport` from portside (browsers cannot reach portside directly). A minimal Python/FastAPI or Node/Express process is sufficient. Python is preferred for consistency with the rest of the stack.

**D2 — Transport retains an internal portside-only fleet data endpoint**
`GET /api/crews` on the transport stays, but moves to an internal-only binding on `ga-portside`. The public `/api/crews` route (currently on the main port behind bearer auth) is removed from transport and re-exposed by lighthouse. External consumers that were calling transport's `/api/crews` should call lighthouse instead.

**D3 — The SPA becomes real files**
`lighthouse/static/` directory: `index.html`, `style.css`, `app.js`. No build step required — vanilla JS as today. The heredoc in `server.py` is deleted.

**D4 — ga-portal routes / and /api/crews to ga-lighthouse**
The existing `ga-lighthouse` Caddy route block is updated to reverse-proxy to the new container instead of `ga-transport`. Auth gating (`forward_auth`) stays at the portal layer — unchanged.

**D5 — ga-lighthouse joins ga-portside only**
Lighthouse does not join `ga-starboard`. It never talks to crew containers directly. All crew data flows through transport's internal API.

## Out of scope

- SSE/WebSocket push (still polling at 5s — future work)
- Lighthouse showing per-crew task detail beyond what `/api/crews` provides (future work, TRN-286 is the foundation)
- Any change to the per-crew KC dashboard proxy chain
