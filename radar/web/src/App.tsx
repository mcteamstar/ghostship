import { useCallback, useEffect, useRef, useState } from "react";
import { fetchFleet } from "./api/endpoints";
import { FleetFilter } from "./components/FleetFilter";
import { FleetSummary } from "./components/FleetSummary";
import { FleetTable } from "./components/FleetTable";
import { StatusBar } from "./components/StatusBar";
import { nextSortDir, type SortDir } from "./fleet/order";
import { useFleet, type FleetFetcher } from "./fleet/useFleet";

export interface AppProps {
  /** Source of the fleet payload. The default polls /api/crews. Tests pass their own. */
  fetcher?: FleetFetcher;
}

/**
 * The Radar page. It owns the state that must survive a fleet refresh: which crews are
 * open, the filter text and the sort. Row-level state lives in each CrewRow.
 */
export function App({ fetcher = fetchFleet }: AppProps) {
  const [openIds, setOpenIds] = useState<ReadonlySet<string>>(() => new Set());
  const [filter, setFilter] = useState("");
  const [sort, setSort] = useState<SortDir>(null);
  const fleet = useFleet(openIds.size, fetcher);
  const deepLinkChecked = useRef(false);

  // Page title: the running count, from the last successful fleet payload.
  useEffect(() => {
    if (!fleet.data) return;
    const running = fleet.data.crews.filter((crew) => crew.status === "running").length;
    document.title = `Fleet Radar (${running} running)`;
  }, [fleet.data]);

  // Deep link: #crew=<id> opens that crew once, after the first successful load.
  useEffect(() => {
    if (deepLinkChecked.current || !fleet.data) return;
    deepLinkChecked.current = true;
    const crewId = /^#crew=(.+)$/.exec(window.location.hash)?.[1];
    if (crewId && fleet.data.crews.some((crew) => crew.crew_id === crewId)) {
      setOpenIds((previous) => new Set(previous).add(crewId));
    }
  }, [fleet.data]);

  // A crew that leaves the fleet is no longer open, so it cannot pause polling forever.
  useEffect(() => {
    if (!fleet.data) return;
    const present = new Set(fleet.data.crews.map((crew) => crew.crew_id));
    setOpenIds((previous) => {
      const kept = [...previous].filter((id) => present.has(id));
      return kept.length === previous.size ? previous : new Set(kept);
    });
  }, [fleet.data]);

  const toggle = useCallback(
    (crewId: string) => {
      const opening = !openIds.has(crewId);
      setOpenIds((previous) => {
        const next = new Set(previous);
        if (opening) next.add(crewId);
        else next.delete(crewId);
        return next;
      });
      history.replaceState(null, "", opening ? `#crew=${crewId}` : window.location.pathname);
    },
    [openIds],
  );

  const onSort = useCallback(() => setSort((current) => nextSortDir(current)), []);

  return (
    <main>
      <div className="header">
        <h1>👻 Ghostship Fleet Radar</h1>
      </div>
      <StatusBar fleet={fleet} />
      {fleet.data ? <FleetSummary data={fleet.data} /> : null}
      <FleetFilter value={filter} onChange={setFilter} />
      <FleetTable
        fleet={fleet}
        filter={filter}
        sort={sort}
        openIds={openIds}
        onToggle={toggle}
        onSort={onSort}
      />
    </main>
  );
}
