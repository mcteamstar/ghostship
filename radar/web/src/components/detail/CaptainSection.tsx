import { TriangleAlert } from "lucide-react";
import type { CaptainState } from "../../api/types";
import { captainIsStale, minutesSinceCheckin } from "../../fleet/crewState";
import { shortId } from "../../format";
import { Timestamp } from "../Timestamp";

export function CaptainSection({ captain }: { captain: CaptainState }) {
  const now = Date.now();
  const stale = captainIsStale(captain, now);
  const minutes = minutesSinceCheckin(captain, now);
  return (
    <>
      <h2 className="detail-section">Captain</h2>
      <table className="detail-table">
        <thead>
          <tr>
            <th>State</th>
            <th>Schedule</th>
            <th>Current task</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>{captain.enabled ? "active" : "paused"}</td>
            <td>{captain.schedule || "—"}</td>
            <td className="mono">{shortId(captain.current_task_id)}</td>
          </tr>
          {captain.last_checkin_at ? (
            <tr>
              <td colSpan={3}>
                <strong>Last check-in:</strong> <Timestamp iso={captain.last_checkin_at} />
              </td>
            </tr>
          ) : null}
          {stale && minutes !== null ? (
            <tr>
              <td colSpan={3} className="captain-stale-warn">
                <TriangleAlert aria-hidden="true" size={15} /> No check-in for {minutes}m — captain may be stalled
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </>
  );
}
