// One fetch wrapper for every Radar read. It classifies each failure so the UI can
// say what happened: an expired portal session is not a parse error, a 502/503/504
// from ga-radar means the transport is down, and a fetch that throws means the
// network failed before any response arrived. A request that never finishes is
// timed out, so a crew section cannot wait forever.

export type RequestErrorKind =
  | "session-expired"
  | "transport-unreachable"
  | "network"
  | "http-error";

export class RequestError extends Error {
  readonly kind: RequestErrorKind;
  readonly status: number | null;

  constructor(kind: RequestErrorKind, message: string, status: number | null = null) {
    super(message);
    this.name = "RequestError";
    this.kind = kind;
    this.status = status;
  }
}

/** ga-radar answers 502, 503 or 504 when it cannot get a result from the transport. */
const TRANSPORT_UNREACHABLE_STATUSES: ReadonlySet<number> = new Set([502, 503, 504]);

/** ga-radar's own proxy timeout is 10 s; the browser gives up at the same point. */
export const REQUEST_TIMEOUT_MS = 10_000;

/**
 * Owns the signal of one request: the caller's cancel, plus the timeout. Call
 * `dispose` once the body has been read so the timer does not outlive the request.
 */
export class RequestGuard {
  readonly signal: AbortSignal;
  private readonly controller = new AbortController();
  private readonly caller: AbortSignal | undefined;
  private readonly onCallerAbort = () => this.controller.abort();
  private readonly timer: ReturnType<typeof setTimeout>;
  private timedOut = false;

  constructor(caller: AbortSignal | undefined, timeoutMs: number = REQUEST_TIMEOUT_MS) {
    this.signal = this.controller.signal;
    this.caller = caller;
    this.timer = setTimeout(() => {
      this.timedOut = true;
      this.controller.abort();
    }, timeoutMs);
    if (caller?.aborted) {
      this.controller.abort();
    } else {
      caller?.addEventListener("abort", this.onCallerAbort, { once: true });
    }
  }

  /** True when the caller cancelled the request, for example because the row closed. */
  get cancelledByCaller(): boolean {
    return this.caller?.aborted === true && !this.timedOut;
  }

  /**
   * The error to throw for a failure during the request. A caller cancel is rethrown
   * unchanged, so the caller can drop it. Anything else becomes a network failure.
   */
  classify(error: unknown): unknown {
    if (this.cancelledByCaller) return error;
    return new RequestError("network", this.timedOut ? "Request timed out" : errorText(error));
  }

  dispose(): void {
    clearTimeout(this.timer);
    this.caller?.removeEventListener("abort", this.onCallerAbort);
  }
}

/**
 * Turns a Response into parsed JSON, or throws a RequestError.
 *
 * Fetch uses redirect "manual", so a redirect to the login page (Caddy's answer to an
 * expired portal session) arrives as an opaque response with no body. A successful
 * response that is an HTML page is the login page served in place of data, so it is a
 * session expiry too. Any other body that is not JSON, such as an empty 200, is an
 * ordinary failed request, never a session expiry.
 */
export async function readJsonResponse<T>(response: Response, guard?: RequestGuard): Promise<T> {
  if (response.type === "opaqueredirect" || response.redirected) {
    throw new RequestError("session-expired", "Session expired", null);
  }
  if (TRANSPORT_UNREACHABLE_STATUSES.has(response.status)) {
    throw new RequestError("transport-unreachable", `HTTP ${response.status}`, response.status);
  }
  if (!response.ok) {
    throw new RequestError("http-error", `HTTP ${response.status}`, response.status);
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("text/html")) {
    throw new RequestError("session-expired", "Session expired", response.status);
  }
  if (!contentType.includes("application/json")) {
    throw new RequestError("http-error", "Non-JSON response", response.status);
  }
  try {
    return (await response.json()) as T;
  } catch (error) {
    if (guard?.cancelledByCaller) throw error;
    if (guard?.signal.aborted) throw new RequestError("network", "Request timed out", response.status);
    throw new RequestError("http-error", "Unexpected response body", response.status);
  }
}

export interface RequestOptions {
  /** Cancels the request when aborted, for example when its crew row closes. */
  signal?: AbortSignal;
  timeoutMs?: number;
}

/**
 * GET a Radar JSON endpoint with the portal session cookie.
 * Rejects with a RequestError, or with the caller's own abort reason when cancelled.
 */
export async function getJson<T>(url: string, options: RequestOptions = {}): Promise<T> {
  const guard = new RequestGuard(options.signal, options.timeoutMs);
  try {
    let response: Response;
    try {
      response = await fetch(url, { credentials: "include", redirect: "manual", signal: guard.signal });
    } catch (error) {
      throw guard.classify(error);
    }
    return await readJsonResponse<T>(response, guard);
  } finally {
    guard.dispose();
  }
}

/** True for a RequestError of the given kind. */
export function isRequestErrorOfKind(error: unknown, kind: RequestErrorKind): boolean {
  return error instanceof RequestError && error.kind === kind;
}

/** A failure as a RequestError. Anything not raised by the wrapper is a bug, shown as an HTTP error. */
export function toRequestError(error: unknown): RequestError {
  if (error instanceof RequestError) return error;
  return new RequestError("http-error", errorText(error));
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
