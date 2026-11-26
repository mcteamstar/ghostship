// Payload shapes for the Radar browser API. They mirror the responses ga-radar
// proxies from ga-transport (see radar/server.py and transport/tools.py). The
// runtime guards in ./guards.ts check the parts the UI cannot render without.

export interface AgentTask {
  task_id?: string | null;
  id?: string | null;
  agent?: string | null;
  done?: boolean | null;
  elapsed_secs?: number | null;
  elapsed?: number | null;
}

export interface CaptainState {
  enabled: boolean;
  schedule?: string | null;
  current_task_id?: string | null;
  last_checkin_at?: string | null;
}

export interface Crew {
  crew_id: string;
  status: string;
  comp?: string | null;
  composition?: string | null;
  acp_backend?: string | null;
  created_at?: string | null;
  last_task_at?: string | null;
  uptime_secs?: number | null;
  gateway_healthy?: boolean | null;
  dashboard_url?: string | null;
  crew_image_version?: string | null;
  agents?: AgentTask[] | null;
  captain?: CaptainState | null;
}

export interface FleetPayload {
  crews: Crew[];
  active_crews?: number | null;
  max_active_crews?: number | null;
  host_memory_available_gb?: number | null;
}

export interface AgentsPayload {
  agents: AgentTask[];
}

export interface MailSubjectsPayload {
  mailboxes: Record<string, string[]>;
}

/** The six persona agents that get an accent colour on task cards. */
export const PERSONA_AGENTS = ["ghost", "spectre", "banshee", "wraith", "reaper", "raven"] as const;
export type PersonaAgent = (typeof PERSONA_AGENTS)[number];

/** Mailboxes in display order, as the transport lists them. */
export const MAILBOX_ORDER = [
  "ghost", "spectre", "banshee", "wraith", "reaper", "raven", "captain", "admiral",
] as const;
