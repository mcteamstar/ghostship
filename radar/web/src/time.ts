import { useEffect, useState } from "react";

/** Fleet data older than this is stale, but only while the last fetch is failing. */
export const STALE_AFTER_MS = 15_000;
/** Fleet data older than this is critically stale, but only while the last fetch is failing. */
export const CRITICAL_AFTER_MS = 30_000;

export type StaleLevel = "stale" | "critical";

/**
 * How old the shown fleet data is, while the latest fetch has failed.
 *
 * Returns null when no fetch is failing (a poll paused by auto-pause is not a
 * failure), when no fetch has ever succeeded, or when the data is still recent.
 */
export function staleLevel(
  now: number,
  lastSuccessAt: number | null,
  failing: boolean,
): StaleLevel | null {
  if (!failing || lastSuccessAt === null) return null;
  const age = now - lastSuccessAt;
  if (age > CRITICAL_AFTER_MS) return "critical";
  if (age > STALE_AFTER_MS) return "stale";
  return null;
}

/** The current time in milliseconds, refreshed every `intervalMs` while mounted. */
export function useNow(intervalMs: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}
