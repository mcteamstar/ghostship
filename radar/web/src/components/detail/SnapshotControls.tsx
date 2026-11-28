import { RefreshCw } from "lucide-react";
import { Timestamp } from "../Timestamp";

export function SnapshotControls({ label, receivedAt, refresh, pending, failed, source }: {
  label: string;
  receivedAt?: number | null;
  refresh?: () => void;
  pending?: boolean;
  failed?: boolean;
  source?: string;
}) {
  return (
    <div className="radar-controls snapshot-controls">
      {receivedAt != null && <small>{source ?? "Updated"} <Timestamp iso={new Date(receivedAt).toISOString()} /></small>}
      {refresh && <button className="radar-action" disabled={pending} onClick={refresh}>
        <RefreshCw aria-hidden="true" size={14} /> {pending ? `Refreshing ${label}…` : failed ? `Retry ${label}` : `Refresh ${label}`}
      </button>}
    </div>
  );
}
