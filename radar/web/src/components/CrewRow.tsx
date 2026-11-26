import type { Crew } from "../api/types";
import { useAuthRefresh } from "../auth/useAuthRefresh";
import { useCrewDetail } from "../detail/useCrewDetail";
import { activeAgents, crewComp, showsGatewayWarning } from "../fleet/crewState";
import { fmtUptime } from "../format";
import { AgentCountBadge, CaptainBadge, GatewayWarning, StatusBadge } from "./Badges";
import { CopyButton } from "./CopyButton";
import { CrewDetail } from "./CrewDetail";
import { Timestamp } from "./Timestamp";

/** Only http and https dashboards are linked. Anything else is shown as no link. */
function DashboardLink({ url }: { url: string | null | undefined }) {
  if (!url || !/^https?:\/\//i.test(url)) return <>—</>;
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      onClick={(event) => event.stopPropagation()}
    >
      open
    </a>
  );
}

export interface CrewRowProps {
  crew: Crew;
  open: boolean;
  /** False when the filter hides the crew. The row stays mounted so its state survives. */
  visible: boolean;
  onToggle: (crewId: string) => void;
}

/**
 * One crew: its summary row and its detail row. The row owns its detail requests and its
 * Refresh auth state, so a fleet refresh re-renders it without losing either. The cells
 * carry their column names, which the narrow layout shows above each value.
 */
export function CrewRow({ crew, open, visible, onToggle }: CrewRowProps) {
  const crewId = crew.crew_id;
  const detailId = `detail-${crewId}`;
  const running = crew.status === "running";
  const detail = useCrewDetail(crewId, open, running);
  const auth = useAuthRefresh(crewId, open);
  const rowClass = ["data-row", open ? "open" : "", running ? "" : "stopped-row"].filter(Boolean).join(" ");

  return (
    <>
      <tr
        className={rowClass}
        role="row"
        data-crew-id={crewId}
        hidden={!visible}
        onClick={() => onToggle(crewId)}
      >
        <td role="cell">
          <button
            type="button"
            className="expand-btn"
            aria-expanded={open}
            aria-controls={detailId}
            aria-label={`${open ? "Collapse" : "Expand"} details for ${crewId}`}
          >
            {open ? "▾" : "▸"}
          </button>{" "}
          <span className="crew-id">{crewId}</span>
          <CopyButton crewId={crewId} />
          <AgentCountBadge count={activeAgents(crew.agents).length} />
          <CaptainBadge captain={crew.captain} />
        </td>
        <td role="cell" data-label="Status">
          <StatusBadge status={crew.status} />
          {showsGatewayWarning(crew) ? (
            <>
              {" "}
              <GatewayWarning />
            </>
          ) : null}
        </td>
        <td role="cell" data-label="Backend">
          {crew.acp_backend || "kiro"}
        </td>
        <td role="cell" data-label="Comp">
          {crewComp(crew)}
        </td>
        <td role="cell" data-label="Uptime">
          {running ? fmtUptime(crew.uptime_secs) : <Timestamp iso={crew.created_at} />}
        </td>
        <td role="cell" data-label="Last task">
          <Timestamp iso={crew.last_task_at} />
        </td>
        <td role="cell" data-label="Dashboard">
          <DashboardLink url={crew.dashboard_url} />
        </td>
      </tr>
      <tr id={detailId} className="detail-row" role="row" hidden={!open || !visible}>
        <td role="cell" colSpan={7}>
          <div className="detail-inner">
            {open ? <CrewDetail crew={crew} detail={detail} auth={auth} /> : null}
          </div>
        </td>
      </tr>
    </>
  );
}
