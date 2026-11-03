/* Radar SPA — fetch and polling. */

import { renderTable } from "./render.js";
import { markFetchOk, clearFetchOk, lastFetchOk } from "./state.js";

const REFRESH_INTERVAL = 5000; // ms
const statusEl = document.getElementById("status");

export function fetchFleet() {
  fetch("/api/crews", { credentials: "include" })
    .then(function (resp) {
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      return resp.json();
    })
    .then(function (data) {
      statusEl.textContent =
        "Refreshed at: " + new Date().toLocaleTimeString();
      statusEl.className = "";
      markFetchOk();
      renderTable(data);
      document.title = "Fleet Radar (" + (data.crews || []).filter(function (c) { return c.status === "running"; }).length + " running)";
      /* Staleness check — clears stale classes when data is fresh. */
      if (lastFetchOk && Date.now() - lastFetchOk > 30000) {
        statusEl.classList.add("stale-critical");
        statusEl.classList.remove("stale");
      } else if (lastFetchOk && Date.now() - lastFetchOk > 15000) {
        statusEl.classList.add("stale");
        statusEl.classList.remove("stale-critical");
      } else {
        statusEl.classList.remove("stale");
        statusEl.classList.remove("stale-critical");
      }
    })
    .catch(function (err) {
      clearFetchOk();
      let msg;
      if (err instanceof TypeError) {
        msg = "Network error — check your connection";
      } else if (err.message && (err.message.includes("502") || err.message.includes("503") || err.message.includes("504"))) {
        msg = "Transport unreachable — check ga-transport is running";
      } else {
        msg = "Fetch error: " + err.message;
      }
      statusEl.textContent = msg;
      statusEl.className = "error";
    });
}

export function startPolling() {
  return setInterval(fetchFleet, REFRESH_INTERVAL);
}
