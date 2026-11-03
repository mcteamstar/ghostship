/* Radar SPA — fetch and polling. */

import { renderTable } from "./render.js";
import { markFetchOk, clearFetchOk } from "./state.js";

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
