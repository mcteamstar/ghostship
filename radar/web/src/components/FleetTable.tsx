import type { Crew } from "../api/types";
import { matchesFilter } from "../fleet/crewState";
import { orderFleet, type SortDir } from "../fleet/order";
import type { FleetState } from "../fleet/useFleet";
import { CrewRow } from "./CrewRow";

export interface FleetTableProps {
  fleet: FleetState;
  /** The filter as typed. Matching is case-insensitive. */
  filter: string;
  sort: SortDir;
  openIds: ReadonlySet<string>;
  onToggle: (crewId: string) => void;
  onSort: () => void;
}

function sortIndicator(sort: SortDir): string {
  if (sort === "desc") return " ▼";
  if (sort === "asc") return " ▲";
  return "";
}

function ariaSort(sort: SortDir): "descending" | "ascending" | "none" {
  if (sort === "desc") return "descending";
  if (sort === "asc") return "ascending";
  return "none";
}

/**
 * The fleet table. Running crews come first, then an "Inactive" divider and the stopped
 * crews. Rows hidden by the filter stay mounted, so an open row keeps its state.
 */
export function FleetTable({ fleet, filter, sort, openIds, onToggle, onSort }: FleetTableProps) {
  const crews: readonly Crew[] = fleet.data?.crews ?? [];
  const needle = filter.toLowerCase();
  const { running, inactive } = orderFleet(crews, sort);
  const matches = (crew: Crew) => matchesFilter(crew, needle);
  const visibleCount = crews.filter(matches).length;
  const visibleInactive = inactive.some(matches);

  let emptyText: string | null = null;
  if (!fleet.data) {
    emptyText = fleet.error ? "Could not load the fleet." : "Fetching fleet data…";
  } else if (crews.length === 0) {
    emptyText = "No crews registered.";
  } else if (visibleCount === 0) {
    emptyText = "No crews match filter.";
  }

  return (
    <div className="table-wrap">
      <table id="fleet-table" role="table">
        <thead role="rowgroup">
          <tr role="row">
            <th scope="col" role="columnheader">Crew</th>
            <th scope="col" role="columnheader">Status</th>
            <th scope="col" role="columnheader">Backend</th>
            <th scope="col" role="columnheader">Comp</th>
            <th scope="col" role="columnheader">Uptime</th>
            <th scope="col" role="columnheader" aria-sort={ariaSort(sort)}>
              <button type="button" className="sort-btn" onClick={onSort}>
                Last Task{sortIndicator(sort)}
              </button>
            </th>
            <th scope="col" role="columnheader">Dashboard</th>
          </tr>
        </thead>
        <tbody id="fleet-body" role="rowgroup">
          {emptyText !== null ? (
            <tr role="row">
              <td role="cell" colSpan={7} className="empty-cell">
                {emptyText}
              </td>
            </tr>
          ) : null}
          {/* One flat list, so a crew keeps its row state when it moves between sections. */}
          {[
            ...running.map((crew) => (
              <CrewRow
                key={crew.crew_id}
                crew={crew}
                open={openIds.has(crew.crew_id)}
                visible={matches(crew)}
                onToggle={onToggle}
              />
            )),
            <tr key="inactive-divider" role="row" className="section-divider" hidden={!visibleInactive}>
              <td role="cell" colSpan={7}>
                Inactive
              </td>
            </tr>,
            ...inactive.map((crew) => (
              <CrewRow
                key={crew.crew_id}
                crew={crew}
                open={openIds.has(crew.crew_id)}
                visible={matches(crew)}
                onToggle={onToggle}
              />
            )),
          ]}
        </tbody>
      </table>
    </div>
  );
}
