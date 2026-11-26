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

/**
 * The line above the fleet: when the data was last refreshed, or the error from the
 * latest fetch. Stale marks apply only while a fetch is failing.
 */
export function StatusBar({ fleet }: { fleet: FleetState }) {
  const now = useNow(1000);
  const level = staleLevel(now, fleet.lastSuccessAt, fleet.error !== null);

  let text: ReactNode;
  let tone = "";
  if (fleet.error) {
    text = <ErrorText error={fleet.error} />;
    const stale = level === "critical" ? "stale-critical" : level === "stale" ? "stale" : "";
    tone = ["error", stale].filter(Boolean).join(" ");
  } else if (fleet.lastSuccessAt !== null) {
    text = `Refreshed at: ${new Date(fleet.lastSuccessAt).toLocaleTimeString()}`;
  } else {
    text = "Loading…";
  }

  return (
    <div id="status-bar" className="status-bar" role="status" aria-live="polite">
      <span id="status-left" className={tone || undefined}>
        {text}
      </span>
    </div>
  );
}
