import { useEffect, useState, type Dispatch, type SetStateAction } from "react";
import { fetchAgents, fetchCrons, fetchMailSubjects } from "../api/endpoints";
import type { RequestError } from "../api/request";
import { toRequestError } from "../api/request";
import type { AgentsPayload, CronsPayload, MailSubjectsPayload } from "../api/types";

/** One detail section's request. `idle` means the section is not requested for this crew. */
export type Section<T> =
  | { state: "idle" }
  | { state: "loading" }
  | { state: "ok"; data: T }
  | { state: "failed"; error: RequestError };

export interface CrewDetailState {
  agents: Section<AgentsPayload>;
  crons: Section<CronsPayload>;
  mail: Section<MailSubjectsPayload>;
}

const IDLE: CrewDetailState = {
  agents: { state: "idle" },
  crons: { state: "idle" },
  mail: { state: "idle" },
};

/**
 * Records the outcome of one section's request, unless the request was cancelled
 * (its row closed or its crew stopped being requested) before it finished.
 */
function settle<T>(
  signal: AbortSignal,
  promise: Promise<T>,
  key: keyof CrewDetailState,
  setDetail: Dispatch<SetStateAction<CrewDetailState>>,
): void {
  const update = (patch: Partial<CrewDetailState>) => {
    if (!signal.aborted) setDetail((previous) => ({ ...previous, ...patch }));
  };
  void promise.then(
    (data) => update({ [key]: { state: "ok", data } } as Partial<CrewDetailState>),
    (error: unknown) => update({ [key]: { state: "failed", error: toRequestError(error) } } as Partial<CrewDetailState>),
  );
}

/**
 * Loads a crew's detail sections while its row is open. Each open fetches a fresh snapshot,
 * and the requests are aborted when the row closes. Mailbox subjects are read for every
 * crew. Agents and scheduled jobs are read only while the crew is running, and they are
 * read again when a crew starts while its row is open, so that section never waits on a
 * request that was never sent.
 *
 * The fleet poll does not restart these requests. The effects depend on `open`, `crewId`
 * and `running` only, so a poll that leaves the crew's status unchanged leaves the open
 * detail alone.
 */
export function useCrewDetail(crewId: string, open: boolean, running: boolean): CrewDetailState {
  const [detail, setDetail] = useState<CrewDetailState>(IDLE);

  useEffect(() => {
    if (!open) {
      setDetail(IDLE);
      return undefined;
    }
    const controller = new AbortController();
    setDetail({ agents: { state: "idle" }, crons: { state: "idle" }, mail: { state: "loading" } });
    settle(controller.signal, fetchMailSubjects(crewId, { signal: controller.signal }), "mail", setDetail);
    return () => controller.abort();
  }, [crewId, open]);

  // Declared after the effect above, so when both run in one commit this loading state wins.
  useEffect(() => {
    if (!open || !running) return undefined;
    const controller = new AbortController();
    setDetail((previous) => ({ ...previous, agents: { state: "loading" }, crons: { state: "loading" } }));
    settle(controller.signal, fetchAgents(crewId, { signal: controller.signal }), "agents", setDetail);
    settle(controller.signal, fetchCrons(crewId, { signal: controller.signal }), "crons", setDetail);
    return () => controller.abort();
  }, [crewId, open, running]);

  return detail;
}
