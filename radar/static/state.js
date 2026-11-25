/* Radar SPA — shared mutable singletons. */

export const openDetails = new Set();
export let lastFetchOk = null;
export let lastData = null;

export function markFetchOk() { lastFetchOk = new Date(); }
export function clearFetchOk() { lastFetchOk = null; }
export function setLastData(d) { lastData = d; }

export let sortDir = null;
export function toggleSortDir() { sortDir = sortDir === null ? "desc" : sortDir === "desc" ? "asc" : null; }

/* Sections fetched on row expand (agents, crons, mail subjects), kept so a
   poll re-render can redraw an open row without fetching again.
   crewId -> { agents, crons, mail } as rendered, already-escaped HTML.
   Cleared on expand and collapse, so reopening a row fetches a fresh snapshot. */
export const detailCache = new Map();
export function cacheDetail(crewId, key, html) {
  if (!openDetails.has(crewId)) return;
  const entry = detailCache.get(crewId) || {};
  entry[key] = html;
  detailCache.set(crewId, entry);
}
export function clearDetailCache(crewId) { detailCache.delete(crewId); }
