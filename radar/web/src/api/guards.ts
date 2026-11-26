// Runtime checks for the parts of each payload the UI renders. A response that fails
// a check becomes a failed read, never an empty section: the transport always sends
// these shapes, so a mismatch means the response is not what Radar asked for.
import { MAILBOX_ORDER, type AgentsPayload, type FleetPayload, type MailSubjectsPayload } from "./types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isFleetPayload(value: unknown): value is FleetPayload {
  return isRecord(value) && Array.isArray(value.crews) && value.crews.every(
    (crew) => isRecord(crew) && typeof crew.crew_id === "string" && typeof crew.status === "string",
  );
}

export function isAgentsPayload(value: unknown): value is AgentsPayload {
  return isRecord(value) && Array.isArray(value.agents) && value.agents.every(isRecord);
}

/** All eight mailboxes must be present as lists of strings. A partial list is not shown. */
export function isMailSubjectsPayload(value: unknown): value is MailSubjectsPayload {
  if (!isRecord(value) || !isRecord(value.mailboxes)) return false;
  const mailboxes = value.mailboxes;
  return MAILBOX_ORDER.every((name) => {
    const subjects = mailboxes[name];
    return Array.isArray(subjects) && subjects.every((s) => typeof s === "string");
  });
}
