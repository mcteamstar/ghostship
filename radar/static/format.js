/* Radar SPA — formatting helpers (pure functions, no DOM). */

export function fmtUptime(secs) {
  if (secs == null) return "—";
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return h + "h " + m + "m";
  if (m > 0) return m + "m " + s + "s";
  return s + "s";
}

export function fmtDate(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    const now = new Date();
    const diffMs = now - d;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHrs  = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    let relative;
    if (diffMins < 1)   relative = "just now";
    else if (diffMins < 60)  relative = diffMins + "m ago";
    else if (diffHrs  < 24)  relative = diffHrs  + "h ago";
    else if (diffDays < 7)   relative = diffDays  + "d ago";
    else relative = d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    return "<span title=\"" + esc(iso) + "\">" + relative + "</span>";
  } catch (e) { return iso; }
}

export function statusBadge(status) {
  const cls =
    status === "running" ? "badge-running" :
    status === "stopped" ? "badge-stopped" : "badge-unknown";
  return "<span class=\"badge " + cls + "\">" + esc(status) + "</span>";
}

export function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function parseInterval(scheduleStr) {
  /* Parses "every Ns" (e.g. "every 300s") → milliseconds; null for anything else. */
  if (!scheduleStr) return null;
  const m = String(scheduleStr).match(/^every\s+(\d+(?:\.\d+)?)s$/i);
  if (!m) return null;
  return parseFloat(m[1]) * 1000;
}
