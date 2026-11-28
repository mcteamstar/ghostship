import { ArrowDown, ArrowLeft, ArrowUp, ChevronsUpDown, ChevronDown, ChevronRight, ExternalLink, LayoutGrid, LayoutList, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { fetchFleet } from "./api/endpoints";
import type { Crew } from "./api/types";
import { useAuthRefresh } from "./auth/useAuthRefresh";
import { CaptainBadge, StatusBadge } from "./components/Badges";
import { CopyButton } from "./components/CopyButton";
import { FleetFilter } from "./components/FleetFilter";
import { FleetSummary } from "./components/FleetSummary";
import { StatusBar } from "./components/StatusBar";
import { Timestamp } from "./components/Timestamp";
import { AgentsSection } from "./components/detail/AgentsSection";
import { CaptainSection } from "./components/detail/CaptainSection";
import { CredentialsSection } from "./components/detail/CredentialsSection";
import { MailHistory } from "./components/detail/MailHistory";
import { useCrewDetail } from "./detail/useCrewDetail";
import { activeAgents, captainIsStale, crewComp, matchesFilter, showsGatewayWarning } from "./fleet/crewState";
import { nextSortDir, orderFleet, type SortDir } from "./fleet/order";
import { useFleet, type FleetFetcher } from "./fleet/useFleet";
import { fmtUptime } from "./format";

const filters = ["All", "Running", "Inactive", "Needs attention"] as const;
type Filter = typeof filters[number];

function matchesStatus(crew: Crew, filter: Filter) {
  if (filter === "All") return true;
  if (filter === "Running") return crew.status === "running";
  if (filter === "Inactive") return crew.status !== "running";
  return (crew.status === "running" && showsGatewayWarning(crew)) || captainIsStale(crew.captain, Date.now());
}

function selectedFromHash() {
  return /^#crew=([a-z0-9-]+)$/.exec(window.location.hash)?.[1] ?? null;
}

function Dashboard({ crew }: { crew: Crew }) {
  return crew.dashboard_url && /^https?:\/\//i.test(crew.dashboard_url)
    ? <a className="radar-action" href={crew.dashboard_url} target="_blank" rel="noopener noreferrer" onClick={event => event.stopPropagation()}><ExternalLink aria-hidden="true" size={16} />Open dashboard</a>
    : null;
}

function Inspector({ crew, open, outside, close }: {
  crew: Crew; open: boolean; outside: boolean; close: () => void;
}) {
  const detail = useCrewDetail(crew.crew_id, open, crew.status === "running", false);
  const auth = useAuthRefresh(crew.crew_id, open);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (open && window.innerWidth < 1100) heading.current?.focus();
  }, [open]);
  if (!open) return null;
  return (
    <aside className="radar-inspector" aria-label="Crew details">
      <header className="radar-inspector-overview">
        <button className="radar-action" onClick={close}><ArrowLeft aria-hidden="true" size={16} />Back to fleet</button>
        <h2 className="radar-inspector-title" tabIndex={-1} ref={heading}>{crew.crew_id}</h2>
        <div className="radar-controls"><StatusBadge status={crew.status} /><Dashboard crew={crew} /><CopyButton crewId={crew.crew_id} /></div>
        {outside && <p className="state">This crew is outside the current results.</p>}
        <dl className="radar-meta">
          <div><dt>Backend</dt><dd>{crew.acp_backend || "kiro"}</dd></div>
          <div><dt>Comp</dt><dd>{crewComp(crew)}</dd></div>
          <div><dt>{crew.status === "running" ? "Uptime" : "Created"}</dt><dd>{crew.status === "running" ? fmtUptime(crew.uptime_secs) : <Timestamp iso={crew.created_at} />}</dd></div>
          <div><dt>Last task</dt><dd><Timestamp iso={crew.last_task_at} /></dd></div>
          {crew.crew_image_version && <div><dt>Image</dt><dd>{crew.crew_image_version}</dd></div>}
        </dl>
        {crew.status === "running" && showsGatewayWarning(crew) && <p className="radar-warning">Gateway unreachable</p>}
        <AgentsSection crew={crew} detail={detail.agents} />
        {crew.captain && <CaptainSection captain={crew.captain} />}
        {crew.status !== "running" && <p className="state">Crew is stopped. Live schedule data is unavailable.</p>}
        <CredentialsSection crewId={crew.crew_id} auth={auth} />
      </header>
      <section className="radar-inspector-body" aria-labelledby={`crew-messages-${crew.crew_id}`}>
        <h3 id={`crew-messages-${crew.crew_id}`}>Messages</h3>
        <MailHistory crewId={crew.crew_id} />
      </section>
    </aside>
  );
}

export function App({ fetcher = fetchFleet }: { fetcher?: FleetFetcher }) {
  const [selected, setSelected] = useState(selectedFromHash);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>("All");
  const [sort, setSort] = useState<SortDir>(null);
  const [mode, setMode] = useState<"List" | "Cards">("List");
  const [notice, setNotice] = useState("");
  const fleet = useFleet(selected ? 1 : 0, fetcher);
  const crews = fleet.data?.crews ?? [];
  const previousSelection = useRef<string | null>(null);
  const listScroll = useRef(0);
  const list = useRef<HTMLElement>(null);

  useEffect(() => {
    const sync = () => setSelected(selectedFromHash());
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  useEffect(() => {
    if (!fleet.data) return;
    document.title = `Fleet Radar (${fleet.data.crews.filter(c => c.status === "running").length} running)`;
    if (selected && !fleet.data.crews.some(c => c.crew_id === selected)) {
      history.replaceState(null, "", location.pathname + location.search);
      setNotice("The selected crew is no longer in the fleet.");
      setSelected(null);
    }
  }, [fleet.data, selected]);

  useEffect(() => {
    if (selected) previousSelection.current = selected;
    else if (previousSelection.current) {
      const control = document.getElementById(`inspect-${previousSelection.current}`) ?? document.getElementById("fleet-filter");
      control?.focus({ preventScroll: true });
      if (list.current) list.current.scrollTop = listScroll.current;
      if (window.innerWidth < 1100) window.scrollTo(0, listScroll.current);
      previousSelection.current = null;
    }
  }, [selected]);

  function select(id: string | null) {
    if (!selected) listScroll.current = window.innerWidth < 1100
      ? window.scrollY : (list.current?.scrollTop ?? 0);
    setNotice("");
    history.pushState(null, "", location.pathname + location.search + (id ? `#crew=${id}` : ""));
    setSelected(id);
  }

  const result = crews.filter(crew => matchesStatus(crew, filter) && matchesFilter(crew, search.toLowerCase()));
  const groups = orderFleet(result, sort);
  const active = crews.find(crew => crew.crew_id === selected);
  const pick = (crew: Crew) => <button id={`inspect-${crew.crew_id}`} className="radar-crew-name expand-btn"
    aria-expanded={selected === crew.crew_id} aria-label={`${selected === crew.crew_id ? "Collapse" : "Expand"} details for ${crew.crew_id}`} onClick={event => { event.stopPropagation(); select(selected === crew.crew_id ? null : crew.crew_id); }}><span className="crew-id">{crew.crew_id}</span>{selected === crew.crew_id ? <ChevronDown aria-hidden="true" size={14} /> : <ChevronRight aria-hidden="true" size={14} />}</button>;
  const state = (crew: Crew) => <><StatusBadge status={crew.status} /> <CaptainBadge captain={crew.captain} />
    {crew.status === "running" && showsGatewayWarning(crew) && <span className="radar-warning"><TriangleAlert aria-hidden="true" size={15} />Gateway unreachable</span>}</>;
  const actions = (crew: Crew) => <div className="radar-controls"><Dashboard crew={crew} /><CopyButton crewId={crew.crew_id} /></div>;

  return (
    <main className="radar-shell">
      <header className="radar-header"><h1>Ghostship Radar</h1>
        {fleet.data && <FleetSummary data={fleet.data} />}<StatusBar fleet={fleet} />
      </header>
      {notice && <p className="radar-notice" role="status">{notice}</p>}
      <div className={active ? "radar-workspace has-crew" : "radar-workspace"}>
        <section ref={list} className="radar-fleet" aria-labelledby="radar-fleet-title">
          <div className="radar-controls radar-title"><h2 id="radar-fleet-title">Fleet</h2>
            <div className="radar-controls" role="group" aria-label="Fleet layout">
              {(["List", "Cards"] as const).map(name => <button key={name} aria-pressed={mode === name} onClick={() => setMode(name)}>{name === "List" ? <LayoutList aria-hidden="true" size={16} /> : <LayoutGrid aria-hidden="true" size={16} />}{name}</button>)}
            </div>
          </div>
          <div className="radar-controls radar-search"><FleetFilter value={search} onChange={setSearch} />
            <label className={mode === "List" ? "radar-list-mobile-sort" : undefined}>Sort <select value={sort ?? ""} onChange={event => setSort(event.target.value === "" ? null : event.target.value === "asc" ? "asc" : "desc")}>
              <option value="">Newest created</option><option value="desc">Last task: newest</option><option value="asc">Last task: oldest</option>
            </select></label>
          </div>
          <div className="radar-controls radar-filters" role="group" aria-label="Crew status filter">
            {filters.map(name => <button key={name} aria-pressed={name === filter} onClick={() => setFilter(name)}>{name}</button>)}
          </div>
          {!fleet.data ? <p>{fleet.error ? "Could not load the fleet." : "Fetching fleet data…"}</p>
            : !crews.length ? <p>No crews registered.</p>
            : !result.length ? <p>No crews match filter. <button onClick={() => { setSearch(""); setFilter("All"); }}>Clear filters</button></p> : null}
          {([["Running", groups.running], ["Inactive", groups.inactive]] as const).map(([label, group]) => group.length > 0 && (
            <section key={label} className="radar-group"><h3>{label} <span>{group.length}</span></h3>
              {mode === "Cards" ? <ul className="radar-cards">
                {group.map(crew => <li key={crew.crew_id} className={crew.crew_id === selected ? "selected" : ""}>
                  <button id={`inspect-${crew.crew_id}`} type="button" className="crew-card-select"
                    aria-expanded={selected === crew.crew_id}
                    aria-label={`${selected === crew.crew_id ? "Collapse" : "Expand"} details for ${crew.crew_id}`}
                    onClick={() => select(selected === crew.crew_id ? null : crew.crew_id)}>
                    <span className="crew-card-heading"><span className="crew-id">{crew.crew_id}</span>{selected === crew.crew_id ? <ChevronDown aria-hidden="true" size={16} /> : <ChevronRight aria-hidden="true" size={16} />}</span>
                    <span className="crew-card-state">{state(crew)}</span>
                    <span>{crewComp(crew)} · {crew.acp_backend || "kiro"}</span>
                    <span>{activeAgents(crew.agents).length} active · Last task <Timestamp iso={crew.last_task_at} /></span>
                  </button>
                  <div className="crew-card-actions">{actions(crew)}</div>
                </li>)}
              </ul> : <table className="radar-list">
                <thead><tr>
                  <th scope="col">Crew</th><th scope="col">Status</th><th scope="col">Active tasks</th>
                  <th scope="col" aria-sort={sort === "desc" ? "descending" : sort === "asc" ? "ascending" : "none"}>
                    <button type="button" className="sort-btn radar-column-sort" onClick={() => setSort(nextSortDir)}>
                      Last task {sort === "desc" ? <ArrowDown aria-hidden="true" size={14} />
                        : sort === "asc" ? <ArrowUp aria-hidden="true" size={14} />
                        : <ChevronsUpDown aria-hidden="true" size={14} />}
                    </button>
                  </th>
                  <th scope="col">Actions</th>
                </tr></thead>
                <tbody>{group.map(crew => <tr key={crew.crew_id} data-crew-id={crew.crew_id} className={crew.crew_id === selected ? "data-row selected" : "data-row"} onClick={() => select(selected === crew.crew_id ? null : crew.crew_id)}>
                  <td>{pick(crew)}<small>{crewComp(crew)} · {crew.acp_backend || "kiro"}</small></td>
                  <td data-label="Status">{state(crew)}</td><td data-label="Active tasks">{activeAgents(crew.agents).length}</td>
                  <td data-label="Last task"><Timestamp iso={crew.last_task_at} /></td><td>{actions(crew)}</td>
                </tr>)}</tbody>
              </table>}
            </section>
          ))}
        </section>
        {crews.map(crew => <Inspector key={crew.crew_id} crew={crew} open={crew.crew_id === selected}
          outside={!result.includes(crew)} close={() => select(null)} />)}
      </div>
    </main>
  );
}
