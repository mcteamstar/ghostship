/* Radar SPA — fetch and polling. */

import { renderTable } from "./render.js";
import { markFetchOk, clearFetchOk, openDetails, lastFetchOk, setLastData } from "./state.js";

const REFRESH_INTERVAL = 5000; // ms
const statusEl = document.getElementById("status");
const capacityEl = document.getElementById("capacity");

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
      document.title = "Fleet Radar (" + (data.crews || []).filter(function (c) { return c.status === "running"; }).length + " running)";
      /* Update capacity display */
      if (capacityEl) {
        const active = data.active_crews || 0;
        const maxCrew = data.max_active_crews;
        const memPart = data.host_memory_available_gb != null
          ? " · " + data.host_memory_available_gb.toFixed(1) + " GB free"
          : "";
        capacityEl.textContent = maxCrew != null
          ? active + " / " + maxCrew + " crews" + memPart
          : "";
      }
      /* Fresh data — clear any staleness indicators. */
      statusEl.classList.remove("stale");
      statusEl.classList.remove("stale-critical");
      /* Re-apply any active filter so poll re-renders don't clear it. */
      const filterEl = document.getElementById("fleet-filter");
      renderTable(data, filterEl ? filterEl.value.toLowerCase() : undefined);
    })
    .catch(function (err) {
      let msg;
      if (err instanceof TypeError) {
        msg = "Network error — check your connection";
      } else if (err.message && (err.message.includes("502") || err.message.includes("503") || err.message.includes("504"))) {
        msg = "Transport unreachable — check ga-transport is running";
      } else {
        msg = "Fetch error: " + err.message;
      }
      statusEl.textContent = msg;
      /* Staleness check — lastFetchOk persists from last success so the
         threshold accumulates across consecutive errors. */
      if (lastFetchOk && Date.now() - lastFetchOk > 30000) {
        statusEl.className = "error stale-critical";
      } else if (lastFetchOk && Date.now() - lastFetchOk > 15000) {
        statusEl.className = "error stale";
      } else {
        statusEl.className = "error";
      }
    });
}

export function startPolling() {
  return setInterval(fetchFleet, REFRESH_INTERVAL);
}
