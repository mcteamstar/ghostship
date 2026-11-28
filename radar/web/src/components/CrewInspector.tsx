import { ArrowLeft, ChevronLeft, ChevronRight, Inbox, PanelsTopLeft, TriangleAlert, X } from "lucide-react";
import { useEffect, useRef } from "react";
import { fetchAgents } from "../api/endpoints";
import type { Crew } from "../api/types";
import { useAuthRefresh } from "../auth/useAuthRefresh";
import { useSnapshot } from "../detail/useSnapshot";
import { crewComp, showsGatewayWarning } from "../fleet/crewState";
import { fmtUptime } from "../format";
import { CaptainBadge, StatusBadge } from "./Badges";
import { CopyButton } from "./CopyButton";
import { Dashboard } from "./DashboardLink";
import { Timestamp } from "./Timestamp";
import { AgentsSection } from "./detail/AgentsSection";
import { CaptainSection } from "./detail/CaptainSection";
import { CredentialsSection } from "./detail/CredentialsSection";
import { MailHistory } from "./detail/MailHistory";
import { SnapshotControls } from "./detail/SnapshotControls";
import { FailedSection } from "./detail/states";

function readTasks(crewId: string, signal: AbortSignal) {
  return fetchAgents(crewId, { signal });
}

function RunningTasks({ crew }: { crew: Crew }) {
  const { snapshot, error, pending, refresh } = useSnapshot(crew.crew_id, readTasks);
  return <>
    <AgentsSection crew={crew} detail={snapshot ? { state: "ok", data: snapshot.data }
      : error ? { state: "failed", error } : { state: "loading" }} />
    <SnapshotControls label="tasks" receivedAt={snapshot?.receivedAt} refresh={refresh}
      pending={pending} failed={!!error} />
    {snapshot && error && <FailedSection error={error}
      unavailable="Could not refresh tasks. Showing the last successful snapshot." />}
  </>;
}

export type DetailView = "Messages" | "Overview";

interface CrewNavigation {
  position: number;
  total: number;
  previous?: Crew;
  next?: Crew;
  select: (id: string) => void;
}

export function CrewInspector({ crew, open, outside, close, fleetUpdatedAt, view, setView, navigation, focusHeading }: {
  crew: Crew;
  open: boolean;
  outside: boolean;
  close: () => void;
  fleetUpdatedAt: number | null;
  view: DetailView;
  setView: (view: DetailView) => void;
  navigation: CrewNavigation;
  focusHeading: boolean;
}) {
  const auth = useAuthRefresh(crew.crew_id, open);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (open && (focusHeading || window.innerWidth < 1100)) heading.current?.focus({ preventScroll: true });
  }, [open, focusHeading]);

  if (!open) return null;
  const { position, total, previous, next, select } = navigation;
  const warning = crew.status === "running" && showsGatewayWarning(crew);
  return (
    <aside className="radar-inspector" id={`details-${crew.crew_id}`} aria-label="Crew details">
      <header className="radar-inspector-overview">
        <div className="inspector-command">
          <button type="button" className="inspector-back" onClick={close}>
            <ArrowLeft aria-hidden="true" size={16} />Back to fleet
          </button>
          <button type="button" className="radar-icon-action inspector-close" onClick={close}
            aria-label="Close crew details" title="Close crew details">
            <X aria-hidden="true" size={18} />
          </button>
          {position >= 0 && total > 1 && <div className="crew-stepper" role="group" aria-label="Browse filtered crews">
            <button type="button" className="radar-icon-action" aria-label="Previous crew" title={previous?.crew_id}
              disabled={!previous} onClick={() => previous && select(previous.crew_id)}><ChevronLeft aria-hidden="true" size={18} /></button>
            <span>{position + 1} of {total}</span>
            <button type="button" className="radar-icon-action" aria-label="Next crew" title={next?.crew_id}
              disabled={!next} onClick={() => next && select(next.crew_id)}><ChevronRight aria-hidden="true" size={18} /></button>
          </div>}
        </div>
        <div className="inspector-identity">
          <h2 className="radar-inspector-title" tabIndex={-1} ref={heading}>{crew.crew_id}</h2>
          <div className="radar-controls inspector-actions">
            <Dashboard crew={crew} />
            <CopyButton crewId={crew.crew_id} />
          </div>
        </div>
        <div className="radar-controls inspector-state">
          <StatusBadge status={crew.status} /><CaptainBadge captain={crew.captain} />
          {warning && <span className="radar-warning"><TriangleAlert size={15} aria-hidden="true" />Gateway unreachable</span>}
        </div>
        {outside && <p className="state">This crew is outside the current results.</p>}
        <div className="radar-controls inspector-views" role="group" aria-label="Crew detail view">
          {(["Messages", "Overview"] as const).map(name => <button key={name} type="button"
            id={`view-${crew.crew_id}-${name}`} aria-controls={`panel-${crew.crew_id}-${name}`}
            aria-pressed={view === name} onClick={() => setView(name)}>
            {name === "Messages" ? <Inbox size={16} aria-hidden="true" /> : <PanelsTopLeft size={16} aria-hidden="true" />}
            {name}
          </button>)}
        </div>
      </header>
      <section className="radar-inspector-body inspector-details" id={`panel-${crew.crew_id}-Overview`}
        aria-label="Crew overview" hidden={view !== "Overview"}>
        <div className="overview-sheet">
          <dl className="radar-meta">
            <div><dt>Backend</dt><dd>{crew.acp_backend || "kiro"}</dd></div>
            <div><dt>Composition</dt><dd>{crewComp(crew)}</dd></div>
            <div><dt>{crew.status === "running" ? "Uptime" : "Created"}</dt><dd>{crew.status === "running" ? fmtUptime(crew.uptime_secs) : <Timestamp iso={crew.created_at} />}</dd></div>
            <div><dt>Last task</dt><dd><Timestamp iso={crew.last_task_at} /></dd></div>
            {crew.crew_image_version && <div><dt>Image</dt><dd>{crew.crew_image_version}</dd></div>}
          </dl>
          <div className="overview-block">
            {crew.status === "running" ? <RunningTasks crew={crew} /> : <>
              <AgentsSection crew={crew} detail={{ state: "idle" }} />
              <SnapshotControls label="tasks" source="Fleet snapshot" receivedAt={fleetUpdatedAt} />
            </>}
          </div>
          {crew.captain && <div className="overview-block">
            <CaptainSection captain={crew.captain} />
          </div>}
          {crew.status !== "running" && <p className="state">Crew is stopped. Live schedule data is unavailable.</p>}
          <div className="overview-block"><CredentialsSection crewId={crew.crew_id} auth={auth} /></div>
        </div>
      </section>
      <section className="radar-inspector-body inspector-messages" id={`panel-${crew.crew_id}-Messages`}
        aria-label="Messages" hidden={view !== "Messages"}>
        <MailHistory crewId={crew.crew_id} />
      </section>
    </aside>
  );
}
