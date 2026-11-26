import { useEffect, useRef, useState } from "react";
import { fetchFleet } from "../api/endpoints";
import { toRequestError, type RequestError } from "../api/request";
import type { FleetPayload } from "../api/types";

/** The fleet is fetched every five seconds. */
export const FLEET_POLL_MS = 5_000;
/**
 * While any crew detail is open, a scheduled fetch is skipped if the last success was
 * this recent. A detail's own requests therefore do not race the fleet refresh.
 */
export const AUTO_PAUSE_MS = 25_000;

export interface FleetState {
  /** The last successful payload. It stays on screen when a later fetch fails. */
  data: FleetPayload | null;
  /** Epoch milliseconds of the last successful fetch, or null before the first one. */
  lastSuccessAt: number | null;
  /** The failure of the most recent attempt. Null after a success. */
  error: RequestError | null;
}

export type FleetFetcher = () => Promise<FleetPayload>;

/**
 * Polls the fleet. Each poll keeps the last good payload, a poll is never started
 * while one is in flight, and a scheduled poll is skipped while a detail is open
 * and the last success is under `AUTO_PAUSE_MS` old.
 */
export function useFleet(openDetailCount: number, fetcher: FleetFetcher = fetchFleet): FleetState {
  const [state, setState] = useState<FleetState>({ data: null, lastSuccessAt: null, error: null });
  const openCountRef = useRef(openDetailCount);
  const lastSuccessRef = useRef<number | null>(null);

  useEffect(() => {
    openCountRef.current = openDetailCount;
  }, [openDetailCount]);

  useEffect(() => {
    let active = true;
    let inFlight = false;

    const poll = async (): Promise<void> => {
      if (inFlight) return;
      const last = lastSuccessRef.current;
      if (openCountRef.current > 0 && last !== null && Date.now() - last < AUTO_PAUSE_MS) {
        return;
      }
      inFlight = true;
      try {
        const data = await fetcher();
        if (!active) return;
        const at = Date.now();
        lastSuccessRef.current = at;
        setState({ data, lastSuccessAt: at, error: null });
      } catch (error) {
        if (!active) return;
        setState((previous) => ({ ...previous, error: toRequestError(error) }));
      } finally {
        inFlight = false;
      }
    };

    void poll();
    const timer = setInterval(() => void poll(), FLEET_POLL_MS);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [fetcher]);

  return state;
}
