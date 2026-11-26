import { isRequestErrorOfKind, type RequestError } from "../../api/request";

/** A detail request that failed because the portal session ended. */
export function SessionExpiredNote() {
  return (
    <p className="state state-session" role="status">
      <strong>Session expired, sign in again</strong> <a href="/dashboard/login">Sign in</a>
    </p>
  );
}

/**
 * A failed detail request, shown as a named state. A session expiry gets its own note;
 * any other failure says the section is unavailable, never that it is empty.
 */
export function FailedSection({ error, unavailable }: { error: RequestError; unavailable: string }) {
  if (isRequestErrorOfKind(error, "session-expired")) return <SessionExpiredNote />;
  return (
    <p className="state state-unavailable" role="status">
      {unavailable}
    </p>
  );
}
