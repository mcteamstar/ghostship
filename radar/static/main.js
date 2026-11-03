/* Radar SPA — entry point. */

import { fetchFleet, startPolling } from "./data.js";

document.addEventListener("DOMContentLoaded", function () {
  fetchFleet();
  startPolling();
});
