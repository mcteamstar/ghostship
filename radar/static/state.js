/* Radar SPA — shared mutable singletons. */

export const openDetails = new Set();
export let lastFetchOk = null;
export let lastData = null;

export function markFetchOk() { lastFetchOk = new Date(); }
export function clearFetchOk() { lastFetchOk = null; }
export function setLastData(d) { lastData = d; }

export let sortDir = null;
export function toggleSortDir() { sortDir = sortDir === null ? "desc" : sortDir === "desc" ? "asc" : null; }
