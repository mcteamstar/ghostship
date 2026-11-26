import { vi, type Mock } from "vitest";
import type { Crew, FleetPayload, MailSubjectsPayload } from "../../src/api/types";
import { MAILBOX_ORDER } from "../../src/api/types";

/** A running crew with the fields the fleet payload always carries. */
export function crew(overrides: Partial<Crew> = {}): Crew {
  return {
    crew_id: "alpha",
    status: "running",
    comp: "spec-ops",
    composition: "spec-ops",
    acp_backend: "kiro",
    created_at: "2026-11-20T10:00:00Z",
    last_task_at: null,
    uptime_secs: 120,
    gateway_healthy: true,
    dashboard_url: null,
    crew_image_version: "0.13.2-spec-ops",
    agents: [],
    captain: null,
    ...overrides,
  };
}

export function fleet(crews: Crew[], overrides: Partial<FleetPayload> = {}): FleetPayload {
  return {
    crews,
    active_crews: 1,
    max_active_crews: 3,
    host_memory_available_gb: 4.1,
    ...overrides,
  };
}

/** All eight mailboxes, each set to `[]` unless overridden. */
export function mailboxes(overrides: Partial<Record<string, string[]>> = {}): MailSubjectsPayload["mailboxes"] {
  const result: Record<string, string[]> = {};
  for (const name of MAILBOX_ORDER) result[name] = overrides[name] ?? [];
  return result;
}

/** A JSON Response with the content type the transport sends. */
export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** An HTML Response, as a login page or a proxy error page is served. */
export function htmlResponse(body: string, status = 200): Response {
  return new Response(body, { status, headers: { "content-type": "text/html; charset=utf-8" } });
}

/** A redirect fetch returns with redirect "manual": opaque, with no status or body. */
export function opaqueRedirect(): Response {
  return {
    type: "opaqueredirect",
    status: 0,
    ok: false,
    redirected: false,
    headers: new Headers(),
    json: () => Promise.reject(new SyntaxError("opaque redirect has no body")),
  } as unknown as Response;
}

/**
 * A route answers one request. It is a factory, not a Response, because a Response
 * body can only be read once and a route may be called on every poll.
 */
export type Route = (url: string, init: RequestInit) => Response | Promise<Response>;

/**
 * Replaces the global fetch with a router. An unmatched URL throws, so a request the UI
 * should not make fails the test instead of being ignored.
 */
export function routeFetch(routes: Record<string, Route>): Mock {
  // Empty detail answers for alpha, used when a test does not care about them. A test
  // that sets its own route for these URLs overrides the default.
  const defaults: Record<string, Route> = {
    "/api/crews/alpha/agents": () => jsonResponse({ agents: [] }),
    "/crews/alpha/api/crons": () => jsonResponse({ jobs: [] }),
  };
  const table = { ...defaults, ...routes };
  const mock = vi.fn(async (url: string, init: RequestInit = {}) => {
    const route = table[url];
    if (route === undefined) throw new Error(`unexpected request: ${init.method ?? "GET"} ${url}`);
    return route(url, init);
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

/** The calls made to a URL, as [init] tuples. */
export function callsTo(mock: Mock, url: string): RequestInit[] {
  return mock.mock.calls.filter((call) => call[0] === url).map((call) => (call[1] ?? {}) as RequestInit);
}
