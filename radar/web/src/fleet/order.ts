// Fleet ordering. Running and inactive crews are sorted separately. The default is
// newest created first; the Last Task sort orders by last task instead. A crew with
// no valid date always sorts after the crews that have one.
import { parseTimestamp } from "../format";
import type { Crew } from "../api/types";

/** null: default ordering. "desc": most recent task first. "asc": least recent first. */
export type SortDir = null | "desc" | "asc";

/** The Last Task header cycles through: none, descending, ascending, none. */
export function nextSortDir(dir: SortDir): SortDir {
  if (dir === null) return "desc";
  if (dir === "desc") return "asc";
  return null;
}

type Compare = (a: Crew, b: Crew) => number;

function byCreatedNewestFirst(a: Crew, b: Crew): number {
  const at = parseTimestamp(a.created_at);
  const bt = parseTimestamp(b.created_at);
  if (at === null) return bt === null ? 0 : 1;
  if (bt === null) return -1;
  return bt - at;
}

function byLastTask(dir: Exclude<SortDir, null>): Compare {
  return (a, b) => {
    const at = parseTimestamp(a.last_task_at);
    const bt = parseTimestamp(b.last_task_at);
    if (at === null && bt === null) return 0;
    if (at === null) return 1;
    if (bt === null) return -1;
    return dir === "desc" ? bt - at : at - bt;
  };
}

export interface OrderedFleet {
  running: Crew[];
  inactive: Crew[];
}

/** Splits the fleet into running and inactive crews, each in the chosen order. */
export function orderFleet(crews: readonly Crew[], sort: SortDir): OrderedFleet {
  const compare: Compare = sort === null ? byCreatedNewestFirst : byLastTask(sort);
  const running = crews.filter((crew) => crew.status === "running").sort(compare);
  const inactive = crews.filter((crew) => crew.status !== "running").sort(compare);
  return { running, inactive };
}
