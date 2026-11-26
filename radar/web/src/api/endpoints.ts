// Radar's browser endpoints. The paths match the routes in radar/server.py.
import type { AgentsPayload, FleetPayload, MailSubjectsPayload } from "./types";
import { RequestError, getJson, type RequestOptions } from "./request";
import { isAgentsPayload, isFleetPayload, isMailSubjectsPayload } from "./guards";

export const FLEET_URL = "/api/crews";

export function agentsUrl(crewId: string): string {
  return `/api/crews/${encodeURIComponent(crewId)}/agents`;
}

export function mailSubjectsUrl(crewId: string): string {
  return `/api/crews/${encodeURIComponent(crewId)}/mail-subjects`;
}

export function refreshAuthUrl(crewId: string): string {
  return `/api/crews/${encodeURIComponent(crewId)}/auth/refresh`;
}

/** A payload that arrives as JSON but has the wrong shape is a failed read, not data. */
function checked<T>(value: unknown, guard: (v: unknown) => v is T, what: string): T {
  if (!guard(value)) {
    throw new RequestError("http-error", `Unexpected ${what} response`);
  }
  return value;
}

export async function fetchFleet(options: RequestOptions = {}): Promise<FleetPayload> {
  const body = await getJson<unknown>(FLEET_URL, options);
  return checked(body, isFleetPayload, "fleet");
}

export async function fetchAgents(crewId: string, options: RequestOptions = {}): Promise<AgentsPayload> {
  const body = await getJson<unknown>(agentsUrl(crewId), options);
  return checked(body, isAgentsPayload, "agents");
}

export async function fetchMailSubjects(
  crewId: string,
  options: RequestOptions = {},
): Promise<MailSubjectsPayload> {
  const body = await getJson<unknown>(mailSubjectsUrl(crewId), options);
  return checked(body, isMailSubjectsPayload, "mailbox");
}
