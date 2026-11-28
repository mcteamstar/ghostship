import { useCallback, useEffect, useRef, useState } from "react";
import { toRequestError, type RequestError } from "../api/request";

interface Snapshot<T> {
  data: T;
  receivedAt: number;
}

export function useSnapshot<T>(crewId: string, read: (crewId: string, signal: AbortSignal) => Promise<T>) {
  const [snapshot, setSnapshot] = useState<Snapshot<T>>();
  const [error, setError] = useState<RequestError>();
  const [pending, setPending] = useState(true);
  const request = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    if (request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setPending(true);
    try {
      const data = await read(crewId, controller.signal);
      if (controller.signal.aborted) return;
      setSnapshot({ data, receivedAt: Date.now() });
      setError(undefined);
    } catch (cause) {
      if (!controller.signal.aborted) setError(toRequestError(cause));
    } finally {
      if (request.current === controller) {
        request.current = null;
        setPending(false);
      }
    }
  }, [crewId, read]);

  useEffect(() => {
    void refresh();
    return () => {
      request.current?.abort();
      request.current = null;
    };
  }, [refresh]);

  return { snapshot, error, pending, refresh };
}
