import { CircleAlert, Flag, TriangleAlert } from "lucide-react";
import type { CaptainState } from "../api/types";
import { captainIsStale } from "../fleet/crewState";

export function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "running" ? "badge-running" : status === "stopped" ? "badge-stopped" : "badge-unknown";
  return <span className={`badge ${tone}`}>{status}</span>;
}

export function GatewayWarning() {
  return (
    <span className="badge badge-warn" title="Gateway unreachable">
      <TriangleAlert aria-hidden="true" size={14} />
    </span>
  );
}

export function AgentCountBadge({ count }: { count: number }) {
  if (count === 0) return null;
  return <span className="agent-count">{count} active</span>;
}

export function CaptainBadge({ captain }: { captain: CaptainState | null | undefined }) {
  if (!captain) return null;
  if (!captain.enabled) return <span className="captain-badge captain-off"><Flag aria-hidden="true" size={14} /> Captain paused</span>;
  const stale = captainIsStale(captain, Date.now());
  return stale ? (
    <span className="captain-badge captain-on captain-stale"><Flag aria-hidden="true" size={14} /> Captain overdue <CircleAlert aria-hidden="true" size={14} /></span>
  ) : (
    <span className="captain-badge captain-on"><Flag aria-hidden="true" size={14} /> Captain active</span>
  );
}
