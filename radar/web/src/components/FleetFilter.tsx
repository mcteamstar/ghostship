import { Search, X } from "lucide-react";
import { useRef } from "react";

/** The crew search matches ID and composition. */
export function FleetFilter({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <Search aria-hidden="true" size={16} />
      <input
        ref={input}
        id="fleet-filter"
        className="fleet-filter"
        type="text"
        placeholder="Find crew…"
        aria-label="Filter crews"
        autoComplete="off"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      {value && <button type="button" className="radar-icon-action clear-search"
        aria-label="Clear crew search" title="Clear crew search" onClick={() => {
          onChange("");
          input.current?.focus();
        }}><X size={15} aria-hidden="true" /></button>}
    </>
  );
}
