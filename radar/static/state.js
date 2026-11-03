/* Radar SPA — shared mutable singletons. */

export const openDetails = new Set();
export let lastFetchOk = null;

export function markFetchOk() { lastFetchOk = new Date(); }
export function clearFetchOk() { lastFetchOk = null; }
