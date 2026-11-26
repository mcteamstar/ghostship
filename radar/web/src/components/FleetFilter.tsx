/**
 * The crew filter. It is always shown. The table matches on crew ID and comp,
 * case-insensitively.
 */
export function FleetFilter({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <input
      id="fleet-filter"
      className="fleet-filter"
      type="text"
      placeholder="Filter crews…"
      aria-label="Filter crews"
      autoComplete="off"
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}
