import { useCallback, useEffect, useRef, useState } from "react";
import { requestAuthRefresh, SLOW_NOTE_MS, type RefreshNotice } from "./refresh";

export interface AuthRefreshState {
  /** A refresh for this crew is in flight. The button is disabled while it is. */
  busy: boolean;
  /** True once the request has been in flight for SLOW_NOTE_MS. Cleared with `busy`. */
  slow: boolean;
  /** The outcome of the last refresh, shown while the row stays open. */
  notice: RefreshNotice | null;
  /** Starts one refresh. A call while one is in flight does nothing. */
  refresh: () => void;
}

/**
 * Per-row state for the Refresh auth action. It belongs to the row, not to the detail
 * panel, so the busy state survives a fleet refresh and a collapse. The notice is
 * cleared when the row collapses, and a result that arrives while the row is closed
 * is discarded.
 */
export function useAuthRefresh(crewId: string, open: boolean): AuthRefreshState {
  const [busy, setBusy] = useState(false);
  const [slow, setSlow] = useState(false);
  const [notice, setNotice] = useState<RefreshNotice | null>(null);
  const busyRef = useRef(false);
  const openRef = useRef(open);

  useEffect(() => {
    openRef.current = open;
    if (!open) setNotice(null);
  }, [open]);

  const refresh = useCallback(() => {
    // A ref, not state: two clicks before a re-render must not send two requests.
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setSlow(false);
    setNotice(null);
    const slowTimer = setTimeout(() => setSlow(true), SLOW_NOTE_MS);
    void requestAuthRefresh(crewId).then((result) => {
      if (openRef.current) setNotice(result);
    }).finally(() => {
      clearTimeout(slowTimer);
      busyRef.current = false;
      setBusy(false);
      setSlow(false);
    });
  }, [crewId]);

  return { busy, slow, notice, refresh };
}
