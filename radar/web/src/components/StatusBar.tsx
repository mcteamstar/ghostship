import type { ReactNode } from "react";
import { RequestError } from "../api/request";
import type { FleetState } from "../fleet/useFleet";
import { staleLevel, useNow } from "../time";

function ErrorText({ error }: { error: RequestError }): ReactNode {
  switch (error.kind) {
    case "session-expired":
      return (
        <>
          <span>Session expired, sign in again</span> <a href="/dashboard/login">Sign in</a>
        </>
      );
    case "transport-unreachable":
      return "Transport unreachable — check ga-transport is running";
    case "network":
      return "Network error — check your connection";
    case "http-error":
      return `Fetch error: ${error.message}`;
  }
}

/** Keep the snapshot time visible while announcing only failures and severity changes. */
export function StatusBar({ fleet }: { fleet: FleetState }) {
  const now = useNow(1000);
  const level = staleLevel(now, fleet.lastSuccessAt, fleet.error !== null);
  const stale = level === "critical" ? "stale-critical" : level === "stale" ? "stale" : "";
  const label = level === "critical" ? "Critically stale" : level === "stale" ? "Stale" : null;

  return (
    <div id="status-bar" className="status-bar">
      {fleet.lastSuccessAt !== null && <time dateTime={new Date(fleet.lastSuccessAt).toISOString()}>
        Refreshed at: {new Date(fleet.lastSuccessAt).toLocaleTimeString()}
      </time>}
      <span id="status-left" role="status" aria-live="polite" className={fleet.error ? ["error", stale].filter(Boolean).join(" ") : undefined}>
        {fleet.error ? <>{label && <strong>{label}. </strong>}<ErrorText error={fleet.error} /></>
          : fleet.lastSuccessAt === null ? "Loading…" : null}
      </span>
    </div>
  );
}
