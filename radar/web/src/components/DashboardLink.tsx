import { ExternalLink } from "lucide-react";
import type { Crew } from "../api/types";

export function Dashboard({ crew, compact }: { crew: Crew; compact?: boolean }) {
  return crew.dashboard_url && /^https?:\/\//i.test(crew.dashboard_url)
    ? <a className={compact ? "radar-icon-action" : "radar-action"} href={crew.dashboard_url}
        aria-label="Open dashboard" title="Open dashboard" target="_blank" rel="noopener noreferrer"
        onClick={event => event.stopPropagation()}>
        <ExternalLink aria-hidden="true" size={16} />{!compact && "Open dashboard"}
      </a>
    : null;
}
