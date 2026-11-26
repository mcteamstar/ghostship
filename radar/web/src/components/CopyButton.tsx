import { useEffect, useRef, useState, type MouseEvent } from "react";

/** How long the confirmation mark stays before the copy icon returns. */
const CONFIRM_MS = 1_500;

/**
 * Copies a crew ID. The click does not reach the row, so copying never expands it.
 * The button shows a check mark for a moment, and a live region announces the copy.
 */
export function CopyButton({ crewId }: { crewId: string }) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => () => clearTimeout(timer.current), []);

  const onClick = (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    // Clipboard access can be refused or absent (insecure origin). Copying is best
    // effort, and the confirmation shows either way, as it always has.
    const write = navigator.clipboard?.writeText(crewId);
    write?.catch(() => undefined);
    setCopied(true);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), CONFIRM_MS);
  };

  return (
    <>
      <button
        type="button"
        className="copy-btn"
        title="Copy crew ID"
        aria-label={`Copy crew ID ${crewId}`}
        onClick={onClick}
      >
        {copied ? "✓" : "⧉"}
      </button>
      <span className="visually-hidden" role="status">
        {copied ? `Copied crew ID ${crewId}` : ""}
      </span>
    </>
  );
}
