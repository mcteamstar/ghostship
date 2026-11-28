import { ExternalLink, Power } from "lucide-react";
import type { Crew } from "../api/types";

export function Dashboard({ crew }: { crew: Crew }) {
  if (!crew.dashboard_url || !/^https?:\/\//i.test(crew.dashboard_url)) return null;

  const stopped = crew.status === "stopped";
  const label = stopped ? "Wake and open dashboard" : "Open dashboard";
  const Icon = stopped ? Power : ExternalLink;
  const shortLabel = stopped ? "Wake & open" : null;

  return (
    <a className={shortLabel ? "radar-action dashboard-action" : "radar-icon-action"} href={crew.dashboard_url}
      aria-label={label} title={`${label} in a new tab`} target="_blank" rel="noopener noreferrer"
      onClick={event => event.stopPropagation()}>
      <Icon aria-hidden="true" size={16} />{shortLabel}
    </a>
  );
}
