
  /* Radar SPA — vanilla JS only (D5: no external dependencies). */
  (function () {
    "use strict";

    const REFRESH_INTERVAL = 5000; // ms
    const statusEl  = document.getElementById("status");
    const bodyEl    = document.getElementById("fleet-body");

    /* ── helpers ─────────────────────────────────────────────────── */

    function fmtUptime(secs) {
      if (secs == null) return "—";
      const h = Math.floor(secs / 3600);
      const m = Math.floor((secs % 3600) / 60);
      const s = secs % 60;
      if (h > 0) return h + "h " + m + "m";
      if (m > 0) return m + "m " + s + "s";
      return s + "s";
    }

    function fmtDate(iso) {
      if (!iso) return "—";
      try {
        const d = new Date(iso);
        const now = new Date();
        const diffMs = now - d;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHrs  = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);
        if (diffMins < 1)   return "just now";
        if (diffMins < 60)  return diffMins + "m ago";
        if (diffHrs  < 24)  return diffHrs  + "h ago";
        if (diffDays < 7)   return diffDays  + "d ago";
        return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
      } catch (e) { return iso; }
    }

    function statusBadge(status) {
      const cls =
        status === "running" ? "badge-running" :
        status === "stopped" ? "badge-stopped" : "badge-unknown";
      return "<span class=\"badge " + cls + "\">" + esc(status) + "</span>";
    }

    function esc(s) {
      return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    /* ── fetch and render fleet ──────────────────────────────────── */

    /* Track which crew detail rows are open across renders. */
    const openDetails = new Set();

    function render(data) {
      const crews = data.crews || [];
      if (crews.length === 0) {
        bodyEl.innerHTML =
          "<tr><td colspan=\"7\" class=\"empty-cell\">No crews registered.</td></tr>";
        return;
      }

      const rows = crews.map(function (crew) {
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
        const captainBadge = cap
          ? (cap.enabled
              ? " <span class=\"captain-badge captain-on\">⚑ captain</span>"
              : " <span class=\"captain-badge captain-off\">⚑ paused</span>")
          : "";

        const isOpen = openDetails.has(crew.crew_id);
        const isStopped = crew.status !== "running";
        const rowClass = "data-row" + (isOpen ? " open" : "") + (isStopped ? " stopped-row" : "");
        const detailClass = "detail-row" + (isOpen ? "" : " hidden");
        return (
          "<tr class=\"" + rowClass + "\" data-crew-id=\"" + esc(crew.crew_id) + "\">" +
          "<td>" + esc(crew.crew_id) + agentBadge + captainBadge + "</td>" +
          "<td>" + statusBadge(crew.status) + "</td>" +
          "<td>" + esc(crew.acp_backend || "kiro") + "</td>" +
          "<td>" + esc(crew.composition || "kirocrew") + "</td>" +
          "<td>" + (isStopped ? "—" : fmtUptime(crew.uptime_secs)) + "</td>" +
          "<td>" + fmtDate(crew.last_task_at) + "</td>" +
          "<td>" + dashLink + "</td>" +
          "</tr>" +
          "<tr class=\"" + detailClass + "\" id=\"detail-" + esc(crew.crew_id) + "\">" +
          "<td colspan=\"7\"><div class=\"detail-inner\">" +
          (isOpen ? renderDetail(crew) : "") +
          "</div></td></tr>"
        );
      });
      bodyEl.innerHTML = rows.join("");

      /* Wire up row-click to toggle detail. */
      bodyEl.querySelectorAll("tr.data-row").forEach(function (tr) {
        tr.addEventListener("click", function () {
          const crewId   = tr.getAttribute("data-crew-id");
          const detailTr = document.getElementById("detail-" + crewId);
          if (!detailTr) return;
          const dataRow  = tr;
          if (detailTr.classList.contains("hidden")) {
            openDetails.add(crewId);
            detailTr.classList.remove("hidden");
            dataRow.classList.add("open");
            const crew = (data.crews || []).find(function (c) {
              return c.crew_id === crewId;
            });
            const inner = detailTr.querySelector(".detail-inner");
            inner.innerHTML = renderDetail(crew);
            if (crew && crew.status === "running") {
              loadCrons(crewId, inner);
            }
          } else {
            openDetails.delete(crewId);
            detailTr.classList.add("hidden");
            dataRow.classList.remove("open");
          }
        });
      });
    }

    function renderDetail(crew) {
      if (!crew) return "<em>No data.</em>";
      const agents = Array.isArray(crew.agents) ? crew.agents : [];
      let html = renderAgents(agents);

      /* Captain state inline */
      const cap = crew.captain;
      if (cap) {
        html += "<div class=\"detail-section\">Captain</div><table class=\"detail-table\">" +
          "<tr><th>State</th><th>Schedule</th><th>Current task</th></tr>" +
          "<tr><td>" + (cap.enabled ? "active" : "paused") + "</td>" +
          "<td>" + esc(cap.schedule || "—") + "</td>" +
          "<td class=\"mono\">" + esc((cap.current_task_id || "—").slice(0, 12)) + "</td>" +
          "</tr></table>";
      }

      if (crew.status !== "running") {
        html += "<br><em class=\"empty-cell\">Crew is stopped — live schedule data unavailable.</em>";
      }
      return html;
    }

    function renderAgents(agents) {
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

    function loadCrons(crewId, container) {
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
          container.innerHTML += html;
        });
    }



    function refresh() {
      fetch("/api/crews", { credentials: "include" })
        .then(function (resp) {
          if (!resp.ok) throw new Error("HTTP " + resp.status);
          return resp.json();
        })
        .then(function (data) {
          statusEl.textContent =
            "Refreshed at: " + new Date().toLocaleTimeString();
          statusEl.className = "";
          render(data);
        })
        .catch(function (err) {
          statusEl.textContent = "Fetch error: " + err;
          statusEl.className = "error";
        });
    }

    refresh();
    setInterval(refresh, REFRESH_INTERVAL);
  })();
  