// Per-crew rules the fleet table and the detail panel share. Each one matches the
// behaviour of the pre-React Radar, so they are checked against it in the tests.
import { parseIntervalMs, parseTimestamp } from "../format";
import type { AgentTask, CaptainState, Crew } from "../api/types";

/** Comp shown for a crew. A crew with no comp is treated as spec-ops. */
export function crewComp(crew: Crew): string {
  return crew.comp || crew.composition || "spec-ops";
}

export function isRunning(crew: Crew): boolean {
  return crew.status === "running";
}

/**
 * A running crew whose gateway is unhealthy shows a warning. A stopped crew never
 * does, because its gateway is expected to be down.
 */
export function showsGatewayWarning(crew: Crew): boolean {
  return crew.status !== "stopped" && crew.gateway_healthy === false;
}

/** Tasks not yet done. This is the count on the "N active" badge. */
export function activeAgents(agents: AgentTask[] | null | undefined): AgentTask[] {
  return (agents ?? []).filter((agent) => !agent.done);
}

/**
 * A captain is stale when its last check-in is more than three of its schedule
 * intervals old. A paused captain, a missing check-in or an unknown schedule is never stale.
 */
export function captainIsStale(captain: CaptainState | null | undefined, now: number): boolean {
  if (!captain || !captain.enabled) return false;
  const lastCheckin = parseTimestamp(captain.last_checkin_at);
  const interval = parseIntervalMs(captain.schedule);
  if (lastCheckin === null || interval === null) return false;
  return now - lastCheckin > interval * 3;
}

/** Whole minutes since the last captain check-in, for the stale warning. */
export function minutesSinceCheckin(captain: CaptainState, now: number): number | null {
  const lastCheckin = parseTimestamp(captain.last_checkin_at);
  if (lastCheckin === null) return null;
  return Math.round((now - lastCheckin) / 60_000);
}

/** Case-insensitive match on crew ID and comp. The filter is expected to be lowercased. */
export function matchesFilter(crew: Crew, filter: string): boolean {
  if (filter === "") return true;
  return (
    crew.crew_id.toLowerCase().includes(filter) ||
    crewComp(crew).toLowerCase().includes(filter)
  );
}
