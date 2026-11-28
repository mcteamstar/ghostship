import { ArrowDown, ArrowUp, ChevronRight, ChevronsUpDown, LayoutGrid, LayoutList, Radar, Search, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { fetchFleet } from "./api/endpoints";
import type { Crew } from "./api/types";
import { CaptainBadge, StatusBadge } from "./components/Badges";
import { CopyButton } from "./components/CopyButton";
import { FleetFilter } from "./components/FleetFilter";
import { FleetSummary } from "./components/FleetSummary";
import { StatusBar } from "./components/StatusBar";
import { Timestamp } from "./components/Timestamp";
import { CrewInspector, type DetailView } from "./components/CrewInspector";
import { Dashboard } from "./components/DashboardLink";
import { activeAgents, captainIsStale, crewComp, matchesFilter, showsGatewayWarning } from "./fleet/crewState";
import { nextSortDir, orderFleet, type SortDir } from "./fleet/order";
import { useFleet, type FleetFetcher } from "./fleet/useFleet";

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

export function App({ fetcher = fetchFleet }: { fetcher?: FleetFetcher }) {
  const [selected, setSelected] = useState(selectedFromHash);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>("All");
  const [sort, setSort] = useState<SortDir>(null);
  const [mode, setMode] = useState<"List" | "Cards">("List");
  const [notice, setNotice] = useState("");
  const [view, setView] = useState<DetailView>("Messages");
  const [focusHeading, setFocusHeading] = useState(false);
  const fleet = useFleet(selected ? 1 : 0, fetcher);
  const crews = fleet.data?.crews ?? [];
  const previousSelection = useRef<string | null>(null);
  const listScroll = useRef(0);
  const list = useRef<HTMLDivElement>(null);

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
      setView("Messages");
      const control = document.getElementById(`inspect-${previousSelection.current}`) ?? document.getElementById("fleet-filter");
      control?.focus({ preventScroll: true });
      if (list.current) list.current.scrollTop = listScroll.current;
      if (window.innerWidth < 1100 && window.scrollY !== listScroll.current) window.scrollTo(0, listScroll.current);
      control?.scrollIntoView?.({ block: "nearest" });
      previousSelection.current = null;
    }
  }, [selected]);

  function select(id: string | null, fromInspector = false) {
    if (!selected) listScroll.current = window.innerWidth < 1100
      ? window.scrollY : (list.current?.scrollTop ?? 0);
    setNotice("");
    setFocusHeading(fromInspector);
    if (id && window.innerWidth < 1100 && window.scrollY) window.scrollTo(0, 0);
    history.pushState(null, "", location.pathname + location.search + (id ? `#crew=${id}` : ""));
    setSelected(id);
  }

  const result = crews.filter(crew => matchesStatus(crew, filter) && matchesFilter(crew, search.toLowerCase()));
  const groups = orderFleet(result, sort);
  const crewCount = `${crews.length} ${crews.length === 1 ? "crew" : "crews"}`;
  const active = crews.find(crew => crew.crew_id === selected);
  const fleetGroups = [
    { label: "Running", crews: groups.running },
    { label: "Inactive", crews: groups.inactive },
  ].filter(group => group.crews.length > 0);
  const ordered = [...groups.running, ...groups.inactive];
  const position = ordered.findIndex(crew => crew.crew_id === selected);
  const navigation = {
    position,
    total: ordered.length,
    previous: position > 0 ? ordered[position - 1] : undefined,
    next: position >= 0 ? ordered[position + 1] : undefined,
    select: (id: string) => select(id, true),
  };
  const toggleCrew = (crew: Crew) => select(selected === crew.crew_id ? null : crew.crew_id);
  const expandProps = (crew: Crew) => ({
    id: `inspect-${crew.crew_id}`,
    "aria-expanded": selected === crew.crew_id,
    "aria-controls": selected === crew.crew_id ? `details-${crew.crew_id}` : undefined,
    "aria-label": `${selected === crew.crew_id ? "Collapse" : "Expand"} details for ${crew.crew_id}`,
  });
  const state = (crew: Crew) => <>
    <StatusBadge status={crew.status} /><CaptainBadge captain={crew.captain} />
    {crew.status === "running" && showsGatewayWarning(crew) &&
      <span className="radar-warning"><TriangleAlert aria-hidden="true" size={15} />Gateway unreachable</span>}
  </>;
  const actions = (crew: Crew, compact = false) => <div className="radar-controls">
    <Dashboard crew={crew} compact={compact} /><CopyButton crewId={crew.crew_id} />
  </div>;

  return (
    <main className="radar-shell">
      <header className="radar-header">
        <h1><Radar size={22} aria-hidden="true" />Ghostship Radar</h1>
        {fleet.data && <FleetSummary data={fleet.data} />}
        <StatusBar fleet={fleet} />
      </header>
      {notice && <p className="radar-notice" role="status">{notice}</p>}
      <div className={active ? "radar-workspace has-crew" : "radar-workspace"}>
        <section className="radar-fleet" aria-labelledby="radar-fleet-title">
          <div className="fleet-toolbar">
            <div className="radar-controls radar-title">
              <div className="fleet-title">
                <h2 id="radar-fleet-title">Fleet</h2>
                {fleet.data && <span className="fleet-result-count">
                  {result.length === crews.length ? crewCount : `${result.length} of ${crewCount}`}
                </span>}
              </div>
              <div className="radar-controls segmented-control fleet-layout" role="group" aria-label="Fleet layout">
                {(["List", "Cards"] as const).map(name => <button type="button" key={name} aria-pressed={mode === name}
                  onClick={() => setMode(name)}>
                  {name === "List" ? <LayoutList aria-hidden="true" size={16} /> : <LayoutGrid aria-hidden="true" size={16} />}
                  {name}
                </button>)}
              </div>
            </div>
            <div className="radar-controls radar-search">
              <div className="fleet-search-field">
                <Search size={16} aria-hidden="true" /><FleetFilter value={search} onChange={setSearch} />
              </div>
              <label className={mode === "List" ? "radar-list-mobile-sort" : undefined}>
                <span className="visually-hidden">Sort</span>
                <select value={sort ?? ""} onChange={event => {
                  const order = event.target.value;
                  setSort(order === "asc" || order === "desc" ? order : null);
                }}>
                  <option value="">Newest created</option>
                  <option value="desc">Last task: newest</option>
                  <option value="asc">Last task: oldest</option>
                </select>
              </label>
            </div>
            <div className="radar-controls radar-filters" role="group" aria-label="Crew status filter">
              {filters.map(name => <button key={name} type="button" aria-pressed={name === filter} onClick={() => setFilter(name)}>
                {name === "Needs attention" && <TriangleAlert size={14} aria-hidden="true" />}{name}
              </button>)}
            </div>
          </div>
          <div className="fleet-results" ref={list}>
            {!fleet.data ? <p className="fleet-empty">{fleet.error ? "Could not load the fleet." : "Fetching fleet data…"}</p>
              : !crews.length ? <p className="fleet-empty">No crews registered.</p>
              : !result.length ? <div className="fleet-empty">
                <p>No crews match filter.</p>
                <button type="button" className="radar-action" onClick={() => {
                  setSearch("");
                  setFilter("All");
                  document.getElementById("fleet-filter")?.focus();
                }}>Clear filters</button>
              </div> : null}
            {mode === "Cards" ? fleetGroups.map(group => (
              <section key={group.label} className="radar-group">
                <h3>{group.label} <span>{group.crews.length}</span></h3>
                <ul className="radar-cards">
                  {group.crews.map(crew => <li key={crew.crew_id} className={crew.crew_id === selected ? "selected" : ""}>
                    <button {...expandProps(crew)} type="button" className="crew-card-select" onClick={() => toggleCrew(crew)}>
                      <span className="crew-card-heading"><span className="crew-id">{crew.crew_id}</span><ChevronRight aria-hidden="true" size={16} /></span>
                      <span className="crew-card-state">
                        {state(crew)}
                      </span>
                      <span>{crewComp(crew)} · {crew.acp_backend || "kiro"}</span>
                      <span>{activeAgents(crew.agents).length} active · Last task <Timestamp iso={crew.last_task_at} /></span>
                    </button>
                    <div className="crew-card-actions">{actions(crew)}</div>
                  </li>)}
                </ul>
              </section>
            )) : !!result.length && <table className="radar-list" aria-label="Fleet crews">
              <thead><tr>
                <th scope="col">Crew</th>
                <th scope="col">Status</th>
                <th scope="col" className="fleet-task-col">Active tasks</th>
                <th scope="col" className="fleet-time-col" aria-sort={sort === "desc" ? "descending" : sort === "asc" ? "ascending" : "none"}>
                  <button type="button" className="sort-btn radar-column-sort" onClick={() => setSort(nextSortDir)}>
                    Last task {sort === "desc" ? <ArrowDown aria-hidden="true" size={14} />
                      : sort === "asc" ? <ArrowUp aria-hidden="true" size={14} />
                      : <ChevronsUpDown aria-hidden="true" size={14} />}
                  </button>
                </th>
                <th scope="col" className="fleet-actions-col">Actions</th>
              </tr></thead>
              {fleetGroups.map(group => <tbody key={group.label}>
                <tr className="fleet-group-row"><td colSpan={5}><h3>{group.label} <span>{group.crews.length}</span></h3></td></tr>
                {group.crews.map(crew => {
                  const taskCount = activeAgents(crew.agents).length;
                  return <tr key={crew.crew_id} data-crew-id={crew.crew_id}
                    className={crew.crew_id === selected ? "data-row selected" : "data-row"}
                    onClick={() => { if (!window.getSelection()?.toString()) toggleCrew(crew); }}>
                    <td>
                      <button {...expandProps(crew)} type="button" className="radar-crew-name expand-btn"
                        onClick={event => { event.stopPropagation(); toggleCrew(crew); }}>
                        <span className="crew-id">{crew.crew_id}</span><ChevronRight aria-hidden="true" size={14} />
                      </button>
                      <small>{crewComp(crew)} · {crew.acp_backend || "kiro"}
                        {!!taskCount && <span className="compact-task-count"> · {taskCount} active</span>}
                      </small>
                    </td>
                    <td data-label="Status"><div className="crew-state">{state(crew)}</div></td>
                    <td className="fleet-task-col" data-label="Active tasks">{taskCount}</td>
                    <td className="fleet-time-col" data-label="Last task"><Timestamp iso={crew.last_task_at} /></td>
                    <td className="fleet-actions-col">{actions(crew, true)}</td>
                  </tr>;
                })}
              </tbody>)}
            </table>}
          </div>
        </section>
        {crews.map(crew => <CrewInspector key={crew.crew_id} crew={crew} open={crew.crew_id === selected}
          fleetUpdatedAt={fleet.lastSuccessAt} outside={!result.includes(crew)} close={() => select(null)}
          view={view} setView={setView} navigation={navigation} focusHeading={focusHeading} />)}
      </div>
    </main>
  );
}
