// The Refresh auth action (TRN-367). Radar asks the transport to re-apply the
// credential stored for a crew. The response is mapped to a notice through a fixed
// table: a label and tone are never taken from the response, so it cannot choose
// markup or a CSS class. The transport's guidance text is shown as plain text.
import { refreshAuthUrl } from "../api/endpoints";

export type RefreshStatus =
  | "refreshed"
  | "pending_on_wake"
  | "current"
  | "recreate_required"
  | "credential_missing"
  | "refresh_failed";

export type Tone = "ok" | "info" | "warn" | "error";

interface OutcomeDefinition {
  tone: Tone;
  label: string;
  text: string;
}

/** The six outcomes the transport reports. `text` is used when the response sends no guidance. */
export const REFRESH_OUTCOMES: Readonly<Record<RefreshStatus, OutcomeDefinition>> = {
  refreshed: {
    tone: "ok",
    label: "Refreshed.",
    text: "The stored credential was injected into the running crew.",
  },
  pending_on_wake: {
    tone: "info",
    label: "Pending until wake.",
    text: "The crew is stopped; it receives the stored credential when it wakes.",
  },
  current: {
    tone: "ok",
    label: "Already current.",
    text: "The crew already uses the stored credential.",
  },
  recreate_required: {
    tone: "warn",
    label: "Recreate required.",
    text: "The crew must be recreated with its workspace preserved. See docs/auth.md.",
  },
  credential_missing: {
    tone: "warn",
    label: "No credential stored.",
    text: "No credential is stored for this crew's backend and profile.",
  },
  refresh_failed: {
    tone: "error",
    label: "Refresh failed.",
    text: "The credential could not be refreshed. Check the transport log, then retry.",
  },
};

/** The keys of REFRESH_OUTCOMES. A Set avoids prototype names such as "constructor". */
const OUTCOME_STATUSES: ReadonlySet<string> = new Set(Object.keys(REFRESH_OUTCOMES));

/**
 * How long Radar waits for an answer before it gives up. Radar's server bound is 60 s
 * (radar/server.py), so this one only fires when the server or the proxy in front of it
 * has stopped answering. The gap keeps a slow but legitimate answer from being cut off.
 */
export const REFRESH_TIMEOUT_MS = 75_000;

/** After this long without an answer the button says the request is still working. */
export const SLOW_NOTE_MS = 10_000;

export type RefreshNotice =
  | { kind: "outcome"; tone: Tone; label: string; guidance: string }
  | { kind: "session-expired" }
  | { kind: "did-not-complete"; reason: string }
  | { kind: "timed-out"; seconds: number }
  | { kind: "unknown" };

export const SESSION_EXPIRED: RefreshNotice = { kind: "session-expired" };
export const RESULT_UNKNOWN: RefreshNotice = { kind: "unknown" };
export const NETWORK_FAILURE: RefreshNotice = {
  kind: "did-not-complete",
  reason: "Network error. Check your connection, then retry.",
};

/** Why a refresh did not complete, from the HTTP status Radar answered with. */
export function failureReason(status: number): string {
  if (status === 403) return "Radar rejected the request (same-origin check).";
  if (status === 502 || status === 503 || status === 504) {
    return "Radar could not get a result from ga-transport. Check that it is running, then retry.";
  }
  return `Unexpected response (HTTP ${status}). Check the transport log, then retry.`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Maps a parsed response body to a notice. An unknown or malformed body is RESULT_UNKNOWN. */
export function noticeFromBody(body: unknown): RefreshNotice {
  if (!isRecord(body)) return RESULT_UNKNOWN;
  const status = body.status;
  if (typeof status !== "string" || !OUTCOME_STATUSES.has(status)) return RESULT_UNKNOWN;
  const outcome = REFRESH_OUTCOMES[status as RefreshStatus];
  const message = body.message;
  const guidance = typeof message === "string" && message !== "" ? message : outcome.text;
  return { kind: "outcome", tone: outcome.tone, label: outcome.label, guidance };
}

/** Maps the Response of the refresh POST to a notice. Never rejects. */
export async function noticeFromResponse(response: Response): Promise<RefreshNotice> {
  // The portal answers an expired session with a redirect to the login page. Fetch
  // is set to "manual", so that arrives as an opaque redirect, not as a result.
  if (response.type === "opaqueredirect" || response.redirected) return SESSION_EXPIRED;
  if (!response.ok) return { kind: "did-not-complete", reason: failureReason(response.status) };
  // A 200 with an HTML page is the login page served in place of the API.
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("text/html")) return SESSION_EXPIRED;
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return RESULT_UNKNOWN;
  }
  return noticeFromBody(body);
}

/**
 * POSTs one refresh for a crew. The request has no body and no headers, so the
 * browser's session cookie is the only credential it carries. The abort signal is
 * the only addition to the TRN-367 request shape.
 *
 * If no answer arrives within `timeoutMs`, the request is aborted and the timeout
 * notice is returned. An answer that arrives after that is ignored.
 */
export async function requestAuthRefresh(
  crewId: string,
  timeoutMs: number = REFRESH_TIMEOUT_MS,
): Promise<RefreshNotice> {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timedOut = new Promise<RefreshNotice>((resolve) => {
    timer = setTimeout(() => {
      resolve({ kind: "timed-out", seconds: Math.round(timeoutMs / 1000) });
      controller.abort();
    }, timeoutMs);
  });
  const answered = (async (): Promise<RefreshNotice> => {
    let response: Response;
    try {
      response = await fetch(refreshAuthUrl(crewId), {
        method: "POST",
        credentials: "include",
        redirect: "manual",
        signal: controller.signal,
      });
    } catch {
      return NETWORK_FAILURE;
    }
    return noticeFromResponse(response);
  })();
  try {
    return await Promise.race([answered, timedOut]);
  } finally {
    clearTimeout(timer);
  }
}
