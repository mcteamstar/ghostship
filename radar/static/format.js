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
    if (diffMins < 1)   return "just now";
    if (diffMins < 60)  return diffMins + "m ago";
    if (diffHrs  < 24)  return diffHrs  + "h ago";
    if (diffDays < 7)   return diffDays  + "d ago";
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
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
