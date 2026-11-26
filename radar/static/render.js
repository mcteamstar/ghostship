/* Radar SPA — DOM builders. */

import { fmtDate, fmtUptime, statusBadge, esc, parseInterval } from "./format.js";
import { openDetails, detailCache, cacheDetail, clearDetailCache, authRefreshing } from "./state.js";
import * as state from "./state.js";

const bodyEl = document.getElementById("fleet-body");

/* ── staleness helper ────────────────────────────────────────── */

function captainIsStale(cap) {
  if (!cap || !cap.enabled || !cap.last_checkin_at) return false;
  const interval = parseInterval(cap.schedule);
  if (interval === null) return false;
  return (Date.now() - new Date(cap.last_checkin_at).getTime()) > interval * 3;
}

function crewComp(crew) {
  return crew.comp || crew.composition || "spec-ops";
}

/* ── row builder ─────────────────────────────────────────────── */

export function buildRow(crew) {
  const dashLink = crew.dashboard_url
    ? "<a href=\"" + esc(crew.dashboard_url) + "\" target=\"_blank\" " +
      "rel=\"noopener noreferrer\">open</a>"
    : "—";
  /* Agents from fleet payload — no extra fetch needed for basic task list. */
  const agents = Array.isArray(crew.agents) ? crew.agents : [];
  const activeAgents = agents.filter(function (a) { return !a.done; });
  const agentBadge = activeAgents.length > 0
    ? " <span class=\"agent-count\">" + activeAgents.length + " active</span>"
    : "";

  /* Captain state badge */
  const cap = crew.captain;
  let captainBadge = "";
  if (cap) {
    if (cap.enabled) {
      const stale = captainIsStale(cap);
      captainBadge = stale
        ? " <span class=\"captain-badge captain-on captain-stale\">⚑ captain ⚠</span>"
        : " <span class=\"captain-badge captain-on\">⚑ captain</span>";
    } else {
      captainBadge = " <span class=\"captain-badge captain-off\">⚑ paused</span>";
    }
  }

  /* Copy crew_id button */
  const copyBtn = "<button class=\"copy-btn\" data-copy=\"" + esc(crew.crew_id) +
    "\" title=\"Copy crew ID\">⧉</button>";

  const isOpen = openDetails.has(crew.crew_id);
  const isStopped = crew.status !== "running";
  const rowClass = "data-row" + (isOpen ? " open" : "") + (isStopped ? " stopped-row" : "");
  const detailClass = "detail-row" + (isOpen ? "" : " hidden");
  return (
    "<tr class=\"" + rowClass + "\" data-crew-id=\"" + esc(crew.crew_id) + "\">" +
    "<td>" + esc(crew.crew_id) + copyBtn + agentBadge + captainBadge + "</td>" +
    "<td>" + statusBadge(crew.status) + (crew.status !== "stopped" && crew.gateway_healthy === false ? " <span class=\"badge badge-warn\" title=\"Gateway unreachable\">⚠</span>" : "") + "</td>" +
    "<td>" + esc(crew.acp_backend || "kiro") + "</td>" +
    "<td>" + esc(crewComp(crew)) + "</td>" +
    "<td>" + (crew.status === "running" ? fmtUptime(crew.uptime_secs) : fmtDate(crew.created_at)) + "</td>" +
    "<td>" + fmtDate(crew.last_task_at) + "</td>" +
    "<td>" + dashLink + "</td>" +
    "</tr>" +
    "<tr class=\"" + detailClass + "\" id=\"detail-" + esc(crew.crew_id) + "\">" +
    "<td colspan=\"7\"><div class=\"detail-inner\">" +
    (isOpen ? renderOpenDetail(crew) : "") +
    "</div></td></tr>"
  );
}

/* ── table render ────────────────────────────────────────────── */

export function renderTable(data, filter) {
  const allCrews = data.crews || [];

  /* Apply optional filter */
  const crews = filter
    ? allCrews.filter(function (c) {
        return c.crew_id.toLowerCase().includes(filter) ||
               crewComp(c).toLowerCase().includes(filter);
      })
    : allCrews;

  if (crews.length === 0) {
    bodyEl.innerHTML =
      "<tr><td colspan=\"7\" class=\"empty-cell\">" +
      (filter ? "No crews match filter." : "No crews registered.") +
      "</td></tr>";
    return;
  }

  const running = crews.filter(function (c) { return c.status === "running"; });
  const stopped = crews.filter(function (c) { return c.status !== "running"; });

  if (state.sortDir === null) {
    const newestFirst = function (a, b) {
      const at = Date.parse(a.created_at);
      const bt = Date.parse(b.created_at);
      if (!Number.isFinite(at)) return Number.isFinite(bt) ? 1 : 0;
      if (!Number.isFinite(bt)) return -1;
      return bt - at;
    };
    running.sort(newestFirst);
    stopped.sort(newestFirst);
  } else {
    const sortFn = function (a, b) {
      const at = a.last_task_at ? new Date(a.last_task_at).getTime() : null;
      const bt = b.last_task_at ? new Date(b.last_task_at).getTime() : null;
      if (at === null && bt === null) return 0;
      if (at === null) return 1;
      if (bt === null) return -1;
      return state.sortDir === "desc" ? bt - at : at - bt;
    };
    running.sort(sortFn);
    stopped.sort(sortFn);
  }

  const runningRows = running.map(buildRow);
  const stoppedRows = stopped.map(buildRow);
  let html = runningRows.join("");
  if (stopped.length > 0) {
    html += "<tr class=\"section-divider\"><td colspan=\"7\">Inactive</td></tr>";
    html += stoppedRows.join("");
  }
  bodyEl.innerHTML = html;

  /* Wire up row-click to toggle detail. */
  bodyEl.querySelectorAll("tr.data-row").forEach(function (tr) {
    tr.addEventListener("click", function () {
      const crewId   = tr.getAttribute("data-crew-id");
      const detailTr = document.getElementById("detail-" + crewId);
      if (!detailTr) return;
      const dataRow  = tr;
      if (detailTr.classList.contains("hidden")) {
        openDetails.add(crewId);
        clearDetailCache(crewId);
        detailTr.classList.remove("hidden");
        dataRow.classList.add("open");
        history.replaceState(null, "", "#crew=" + crewId);
        const crew = (data.crews || []).find(function (c) {
          return c.crew_id === crewId;
        });
        const inner = detailTr.querySelector(".detail-inner");
        inner.innerHTML = renderDetail(crew);
        if (crew && crew.status === "running") {
          loadCrons(crewId, inner);
          loadAgents(crewId, inner);
        }
        /* Mailbox subjects load on expansion for running and stopped crews only. */
        if (crew) loadMailSubjects(crewId, inner);
      } else {
        openDetails.delete(crewId);
        clearDetailCache(crewId);
        detailTr.classList.add("hidden");
        dataRow.classList.remove("open");
        history.replaceState(null, "", location.pathname);
      }
    });
  });

  /* Update "Last Task" header text and wire its sort click once. */
  const lastTaskTh = document.querySelector("#fleet-table th.sortable");
  if (lastTaskTh) {
    const indicator = state.sortDir === "desc" ? " ▼" : state.sortDir === "asc" ? " ▲" : "";
    lastTaskTh.textContent = "Last Task" + indicator;
    if (!lastTaskTh.dataset.sortWired) {
      lastTaskTh.dataset.sortWired = "1";
      lastTaskTh.addEventListener("click", function () {
        state.toggleSortDir();
        var filterEl = document.getElementById("fleet-filter");
        renderTable(state.lastData, filterEl ? filterEl.value.toLowerCase() : undefined);
      });
    }
  }
}

/* ── detail panels ───────────────────────────────────────────── */

export function renderOpenDetail(crew) {
  /* Draws an open row on a poll re-render: fleet data plus the sections
     already fetched when the row was expanded. Never fetches. */
  const cached = (crew && detailCache.get(crew.crew_id)) || {};
  return renderDetail(crew, cached.agents) + (cached.crons || "") + (cached.mail || "");
}

function redrawOpenDetail(crewId) {
  /* A fetch that resolves after a poll re-render holds a detached container;
     redraw the live row from cache instead. */
  if (!openDetails.has(crewId) || !state.lastData) return;
  const crew = (state.lastData.crews || []).find(function (c) { return c.crew_id === crewId; });
  const detailTr = document.getElementById("detail-" + crewId);
  const inner = detailTr && detailTr.querySelector ? detailTr.querySelector(".detail-inner") : null;
  if (crew && inner) inner.innerHTML = renderOpenDetail(crew);
}

export function renderDetail(crew, agentsHtml) {
  if (!crew) return "<em>No data.</em>";
  const agents = Array.isArray(crew.agents) ? crew.agents : [];
  const imageHtml = crew.crew_image_version
    ? "<div class=\"detail-image-version\">Image: <span class=\"mono\">" + esc(crew.crew_image_version) + "</span></div>"
    : "";
  let html = imageHtml + (agentsHtml || renderAgents(agents));

  /* Captain state inline */
  const cap = crew.captain;
  if (cap) {
    const checkinRow = cap.last_checkin_at
      ? "<tr><td colspan=\"3\"><strong>Last check-in:</strong> " +
        fmtDate(cap.last_checkin_at) + "</td></tr>"
      : "";
    let staleWarnRow = "";
    if (captainIsStale(cap)) {
      const elapsedMs = Date.now() - new Date(cap.last_checkin_at).getTime();
      const mins = Math.round(elapsedMs / 60000);
      staleWarnRow = "<tr><td colspan=\"3\" class=\"captain-stale-warn\">" +
        "⚠ No check-in for " + mins + "m — captain may be stalled</td></tr>";
    }
    html += "<div class=\"detail-section\">Captain</div><table class=\"detail-table\">" +
      "<tr><th>State</th><th>Schedule</th><th>Current task</th></tr>" +
      "<tr><td>" + (cap.enabled ? "active" : "paused") + "</td>" +
      "<td>" + esc(cap.schedule || "—") + "</td>" +
      "<td class=\"mono\">" + esc((cap.current_task_id || "—").slice(0, 12)) + "</td>" +
      "</tr>" + checkinRow + staleWarnRow + "</table>";
  }

  if (crew.status !== "running") {
    html += "<br><em class=\"empty-cell\">Crew is stopped — live schedule data unavailable.</em>";
  }
  return html + renderAuthRefresh(crew.crew_id);
}

/* ── credential refresh (TRN-367) ────────────────────────────── */

/* Outcomes the transport reports for POST /api/crews/{id}/auth/refresh. Label and tone
   come from this fixed table, never from the response, so the response cannot choose
   markup or a CSS class. The transport's own guidance (esc'd) is shown beside the label;
   the default text is used only if a response carries none. */
const AUTH_REFRESH_OUTCOMES = {
  refreshed: {
    tone: "ok", label: "Refreshed.",
    text: "The stored credential was injected into the running crew.",
  },
  pending_on_wake: {
    tone: "info", label: "Pending until wake.",
    text: "The crew is stopped; it receives the stored credential when it wakes.",
  },
  current: {
    tone: "ok", label: "Already current.",
    text: "The crew already uses the stored credential.",
  },
  recreate_required: {
    tone: "warn", label: "Recreate required.",
    text: "The crew must be recreated with its workspace preserved. See docs/auth.md.",
  },
  credential_missing: {
    tone: "warn", label: "No credential stored.",
    text: "No credential is stored for this crew's backend and profile.",
  },
  refresh_failed: {
    tone: "error", label: "Refresh failed.",
    text: "The credential could not be refreshed. Check the transport log, then retry.",
  },
};

function authNotice(tone, label, text) {
  return "<div class=\"auth-refresh-result auth-" + tone + "\" role=\"status\">" +
    "<strong>" + esc(label) + "</strong> " + esc(text) + "</div>";
}

function authSessionExpiredHtml() {
  /* Caddy answers an expired portal session with a redirect to the login page, which is
     not a refresh outcome and must never be shown as one. */
  return "<div class=\"auth-refresh-result auth-warn\" role=\"status\">" +
    "<strong>Session expired.</strong> Your portal session has ended, so nothing was " +
    "refreshed. <a href=\"/dashboard/login\">Sign in again</a>, then retry.</div>";
}

function authFailureText(httpStatus) {
  if (httpStatus === 403) return "Radar rejected the request (same-origin check).";
  if (httpStatus === 502 || httpStatus === 503 || httpStatus === 504) {
    return "Radar could not get a result from ga-transport. Check that it is running, then retry.";
  }
  return "Unexpected response (HTTP " + httpStatus + "). Check the transport log, then retry.";
}

function authRefreshResultHtml(resp) {
  /* Maps a fetch Response to the result markup. Resolves to a string, never throws. */
  if (resp.type === "opaqueredirect" || resp.redirected) return authSessionExpiredHtml();
  if (!resp.ok) return authNotice("error", "Refresh did not complete.", authFailureText(resp.status));
  const type = (resp.headers && resp.headers.get && resp.headers.get("content-type")) || "";
  /* A 200 HTML page is the login page served instead of the API. */
  if (type.indexOf("text/html") !== -1) return authSessionExpiredHtml();
  return resp.json().then(function (data) {
    const known = data && typeof data.status === "string" &&
      Object.prototype.hasOwnProperty.call(AUTH_REFRESH_OUTCOMES, data.status);
    if (!known) return authNotice("error", "Refresh result unknown.", "The response was not recognised. Retry.");
    const outcome = AUTH_REFRESH_OUTCOMES[data.status];
    const guidance = typeof data.message === "string" && data.message ? data.message : outcome.text;
    return authNotice(outcome.tone, outcome.label, guidance);
  }, function () {
    return authNotice("error", "Refresh result unknown.", "The response was not recognised. Retry.");
  });
}

export function renderAuthRefresh(crewId) {
  /* The "Credentials" section: the refresh button plus the last outcome for this open row. */
  const busy = authRefreshing.has(crewId);
  const cached = detailCache.get(crewId) || {};
  return "<div class=\"detail-section\">Credentials</div>" +
    "<div class=\"auth-refresh\">" +
    "<button type=\"button\" class=\"auth-refresh-btn\" data-auth-refresh=\"" + esc(crewId) + "\"" +
    " title=\"Re-apply this crew's assigned credential if it can be refreshed in place\"" +
    (busy ? " disabled aria-busy=\"true\"" : "") + ">" +
    (busy ? "Refreshing…" : "Refresh auth") + "</button>" +
    (cached.auth || "") + "</div>";
}

export function refreshCrewAuth(crewId) {
  /* Asks Radar to refresh one crew's assigned credential. The request carries no body:
     Radar and the transport use only the crew id, so nothing sensitive is sent. A second
     call while one is in flight does nothing. The outcome is cached for the open row so a
     poll re-render redraws it rather than dropping it. Resolves to the result markup. */
  if (authRefreshing.has(crewId)) return Promise.resolve(null);
  authRefreshing.add(crewId);
  cacheDetail(crewId, "auth", "");
  redrawOpenDetail(crewId);
  let request;
  try {
    /* redirect "manual": an expired portal session answers with a redirect to the login
       page; following it would hand this code the login page as a "response". */
    request = fetch("/api/crews/" + encodeURIComponent(crewId) + "/auth/refresh", {
      method: "POST", credentials: "include", redirect: "manual",
    });
  } catch (err) {
    request = Promise.reject(err);
  }
  return request
    .then(authRefreshResultHtml)
    .catch(function () {
      return authNotice("error", "Refresh did not complete.", "Network error. Check your connection, then retry.");
    })
    .then(function (html) {
      authRefreshing.delete(crewId);
      cacheDetail(crewId, "auth", html);
      redrawOpenDetail(crewId);
      return html;
    });
}

export function wireAuthRefresh(root) {
  /* One delegated listener on the stable <tbody>: the rows inside are replaced on every
     fleet poll, so listeners attached to the buttons themselves would be lost. */
  root.addEventListener("click", function (e) {
    const btn = e.target && e.target.closest ? e.target.closest("[data-auth-refresh]") : null;
    if (!btn) return;
    e.stopPropagation();
    refreshCrewAuth(btn.dataset.authRefresh);
  });
}

export function renderAgents(agents) {
  if (!agents || agents.length === 0) {
    return "<em>No active tasks.</em>";
  }
  let html = "<div class=\"detail-section\">Active tasks</div><table class=\"detail-table\">" +
    "<tr><th>ID</th><th>Agent</th><th>Done</th><th>Elapsed</th></tr>";
  agents.forEach(function (a) {
    html +=
      "<tr><td class=\"mono\">" + esc((a.task_id || a.id || "—").slice(0, 12)) + "</td>" +
      "<td>" + esc(a.agent || "—") + "</td>" +
      "<td>" + (a.done ? "✓" : "<span class=\"running-dot\">●</span>") + "</td>" +
      "<td>" + (a.done && !(a.elapsed_secs || a.elapsed) ? "—" : fmtUptime(a.elapsed_secs || a.elapsed)) + "</td></tr>";
  });
  return html + "</table>";
}

export function loadCrons(crewId, container) {
  /* Fetches non-captain gateway cron jobs. Captain state is rendered
     inline by renderDetail from the fleet payload. */
  const cronsUrl = "/crews/" + encodeURIComponent(crewId) + "/api/crons";
  fetch(cronsUrl, { credentials: "include" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .catch(function () { return null; })
    .then(function (cronsData) {
      const jobs = cronsData && Array.isArray(cronsData.jobs)
        ? cronsData.jobs.filter(function (j) { return j.type !== "captain"; })
        : [];
      if (jobs.length === 0) return;
      let html = "<div class=\"detail-section\">Scheduled jobs</div><table class=\"detail-table\">" +
        "<tr><th>Name</th><th>Agent</th><th>Schedule</th></tr>";
      jobs.forEach(function (j) {
        html +=
          "<tr><td>" + esc(j.name || "—") + "</td>" +
          "<td>" + esc(j.agent || "—") + "</td>" +
          "<td>" + esc(j.schedule || j.cron_expr || "—") + "</td></tr>";
      });
      html += "</table>";
      cacheDetail(crewId, "crons", html);
      if (container.isConnected === false) { redrawOpenDetail(crewId); return; }
      container.innerHTML += html;
    });
}

export function loadAgents(crewId, container) {
  /* Fetches live task list for a running crew on row expand (TRN-304).
     On success: removes the "No active tasks." placeholder and prepends the
     agents table before the captain section.
     On error or empty agents: no-op (existing "No active tasks." placeholder remains). */
  const agentsUrl = "/api/crews/" + encodeURIComponent(crewId) + "/agents";
  fetch(agentsUrl)
    .then(function (r) { return r.ok ? r.json() : null; })
    .catch(function () { return null; })
    .then(function (data) {
      if (!data || !Array.isArray(data.agents) || data.agents.length === 0) return;
      const html = renderAgents(data.agents);
      cacheDetail(crewId, "agents", html);
      if (container.isConnected === false) { redrawOpenDetail(crewId); return; }
      /* Remove the "No active tasks." placeholder set by the initial renderDetail call. */
      container.querySelectorAll("em").forEach(function (em) {
        if (em.textContent === "No active tasks.") em.remove();
      });
      /* Insert before the captain section if present; otherwise prepend. */
      const captainSection = container.querySelector(".detail-section");
      if (captainSection) {
        captainSection.insertAdjacentHTML("beforebegin", html);
      } else {
        container.insertAdjacentHTML("afterbegin", html);
      }
    });
}

/* Mailbox names shown in the expanded detail, in display order (TRN-370). */
const MAILBOX_ORDER = ["ghost", "spectre", "banshee", "wraith", "reaper", "raven", "captain", "admiral"];

export function renderMailSubjects(mailboxes) {
  /* Renders {mailbox: [subject, ...]} grouped by mailbox. Subjects are escaped. */
  let html = "<div class=\"detail-section\">Mailbox subjects</div>";
  MAILBOX_ORDER.forEach(function (name) {
    const subjects = Array.isArray(mailboxes[name]) ? mailboxes[name] : [];
    html += "<div class=\"mail-mailbox\"><strong>" + esc(name) + "</strong>";
    if (subjects.length === 0) {
      html += " <em class=\"empty-cell\">No messages.</em>";
    } else {
      html += "<ul class=\"mail-subjects\">";
      subjects.forEach(function (s) {
        html += "<li>" + esc(s) + "</li>";
      });
      html += "</ul>";
    }
    html += "</div>";
  });
  return html;
}

export function renderMailSubjectsUnavailable() {
  /* One state for the whole crew: a failed read is never shown as empty mailboxes. */
  return "<div class=\"detail-section\">Mailbox subjects</div>" +
    "<em class=\"empty-cell\">Mailbox subjects unavailable.</em>";
}

export function loadMailSubjects(crewId, container) {
  /* Fetches mailbox subjects on row expand (TRN-370). Never called from fleet polling. */
  const mailUrl = "/api/crews/" + encodeURIComponent(crewId) + "/mail-subjects";
  return fetch(mailUrl, { credentials: "include" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .catch(function () { return null; })
    .then(function (data) {
      const valid = data && data.mailboxes && typeof data.mailboxes === "object";
      const html = valid ? renderMailSubjects(data.mailboxes) : renderMailSubjectsUnavailable();
      cacheDetail(crewId, "mail", html);
      if (container.isConnected === false) { redrawOpenDetail(crewId); return; }
      container.insertAdjacentHTML("beforeend", html);
    });
}
