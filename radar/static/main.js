/* Radar SPA — entry point. */

import { fetchFleet, startPolling } from "./data.js";
import * as state from "./state.js";
import { renderTable } from "./render.js";

const bodyEl = document.getElementById("fleet-body");

document.addEventListener("DOMContentLoaded", function () {
  /* Delegated copy-to-clipboard handler.
     Uses capture phase so it fires before the row expand/collapse
     bubbling listener and can stop further propagation. */
  bodyEl.addEventListener("click", function (e) {
    const btn = e.target.closest("[data-copy]");
    if (!btn) return;
    e.stopPropagation();
    navigator.clipboard.writeText(btn.dataset.copy).catch(function () {});
    const orig = btn.textContent;
    btn.textContent = "✓";
    setTimeout(function () { btn.textContent = orig; }, 1500);
  }, true);

  /* Initial fetch; wire up search filter if fleet has >8 crews. */
  const p = fetchFleet();
  if (p && typeof p.then === "function") {
    p.then(function () {
      if (state.lastData && Array.isArray(state.lastData.crews) &&
          state.lastData.crews.length > 8 &&
          !document.getElementById("fleet-filter")) {
        const input = document.createElement("input");
        input.id = "fleet-filter";
        input.placeholder = "Filter crews…";
        const tableWrap = document.querySelector(".table-wrap");
        if (tableWrap) {
          tableWrap.parentNode.insertBefore(input, tableWrap);
        }
        input.addEventListener("input", function (e) {
          renderTable(state.lastData, e.target.value.toLowerCase());
        });
      }
    });
  }
  startPolling();
});
