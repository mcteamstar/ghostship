import { LoaderCircle, RefreshCw, RotateCcw } from "lucide-react";
import { Timestamp } from "../Timestamp";

export function SnapshotControls({ label, receivedAt, refresh, pending, failed, source }: {
  label: string;
  receivedAt?: number | null;
  refresh?: () => void;
  pending?: boolean;
  failed?: boolean;
  source?: string;
}) {
  const action = pending ? `Refreshing ${label}…` : failed ? `Retry ${label}` : `Refresh ${label}`;
  const Icon = pending ? LoaderCircle : failed ? RotateCcw : RefreshCw;
  return (
    <div className="radar-controls snapshot-controls">
      {receivedAt != null && <small>
        <span className="snapshot-source">{source ?? "Updated"} </span>
        <Timestamp iso={new Date(receivedAt).toISOString()} />
      </small>}
      {refresh && <button type="button" className="radar-icon-action snapshot-refresh" disabled={pending}
        aria-label={action} title={action} onClick={refresh}>
        <Icon aria-hidden="true" size={16} />
      </button>}
    </div>
  );
}
