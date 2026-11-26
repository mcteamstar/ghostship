import type { FleetPayload } from "../api/types";

/**
 * Running and stopped counts, then capacity and free memory. A value the fleet does not
 * report is left out, not shown as a placeholder.
 */
export function FleetSummary({ data }: { data: FleetPayload }) {
  const running = data.crews.filter((crew) => crew.status === "running").length;
  const items: Array<[string, string]> = [
    ["Running", String(running)],
    ["Stopped", String(data.crews.length - running)],
  ];
  if (data.max_active_crews !== null && data.max_active_crews !== undefined) {
    items.push(["Capacity", `${data.active_crews ?? 0} / ${data.max_active_crews} crews`]);
  }
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
