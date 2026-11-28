import type { FleetPayload } from "../api/types";

/**
 * Show the capacity limit next to the running count when it is available.
 * Use the same running count as the fleet list.
 */
export function FleetSummary({ data }: { data: FleetPayload }) {
  const running = data.crews.filter((crew) => crew.status === "running").length;
  const maximum = data.max_active_crews;
  const items: Array<[string, string]> = [
    ["Active", maximum == null ? String(running) : `${running} / ${maximum}`],
    ["Asleep", String(data.crews.filter(crew => crew.status === "stopped").length)],
  ];
  if (data.host_memory_available_gb !== null && data.host_memory_available_gb !== undefined) {
    items.push(["Free memory", `${data.host_memory_available_gb.toFixed(1)} GB`]);
  }
  return (
    <dl className="fleet-summary" aria-label="Fleet summary">
      {items.map(([label, value]) => (
        <div className="summary-item" key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}
