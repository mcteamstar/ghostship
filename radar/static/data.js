/* Radar SPA — fetch and polling. */

import { renderTable } from "./render.js";
import { markFetchOk, clearFetchOk, openDetails, lastFetchOk, setLastData } from "./state.js";

const REFRESH_INTERVAL = 5000; // ms
const statusEl = document.getElementById("status");

export function fetchFleet() {
  /* Auto-pause: if a detail row is open and last fetch succeeded <25s ago, skip. */
  if (openDetails.size > 0 && lastFetchOk && Date.now() - lastFetchOk < 25000) return;
  return fetch("/api/crews", { credentials: "include" })
    .then(function (resp) {
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      return resp.json();
    })
    .then(function (data) {
      statusEl.textContent =
        "Refreshed at: " + new Date().toLocaleTimeString();
      statusEl.className = "";
      markFetchOk();
      setLastData(data);
      renderTable(data);
    })
    .catch(function (err) {
      clearFetchOk();
      statusEl.textContent = "Fetch error: " + err;
      statusEl.className = "error";
    });
}

export function startPolling() {
  return setInterval(fetchFleet, REFRESH_INTERVAL);
}
