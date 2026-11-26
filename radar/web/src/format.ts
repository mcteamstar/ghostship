// Formatting helpers. Pure functions, so they are tested without a DOM.

/** "every 600s" becomes 600000 milliseconds. Any other schedule text gives null. */
export function parseIntervalMs(schedule: string | null | undefined): number | null {
  if (!schedule) return null;
  const match = /^every\s+(\d+(?:\.\d+)?)s$/i.exec(schedule);
  if (!match || match[1] === undefined) return null;
  return Number.parseFloat(match[1]) * 1000;
}

/** Elapsed seconds as "1h 2m", "3m 4s" or "5s". Null or missing gives an em dash. */
export function fmtUptime(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${secs}s`;
  return `${secs}s`;
}

/** A timestamp in milliseconds, or null when the text is missing or not a date. */
export function parseTimestamp(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const time = Date.parse(iso);
  return Number.isFinite(time) ? time : null;
}

/** "3m ago", "2h ago", "4d ago", or a short date after a week. Null when not a date. */
export function relativeTime(iso: string | null | undefined, now: number): string | null {
  const time = parseTimestamp(iso);
  if (time === null) return null;
  const diffMs = now - time;
  const minutes = Math.floor(diffMs / 60_000);
  const hours = Math.floor(diffMs / 3_600_000);
  const days = Math.floor(diffMs / 86_400_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;
  return new Date(time).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** Shortens an ID to the first 12 characters, as the detail tables always have. */
export function shortId(id: string | null | undefined): string {
  return (id || "—").slice(0, 12);
}
