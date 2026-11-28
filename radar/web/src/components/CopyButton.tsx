import { Check, CircleAlert, Copy } from "lucide-react";
import { useEffect, useRef, useState, type MouseEvent } from "react";

/** How long the confirmation mark stays before the copy icon returns. */
const CONFIRM_MS = 1_500;

/**
 * Copies a crew ID. The click does not reach the row, so copying never expands it.
 * The button shows a check mark for a moment, and a live region announces the copy.
 */
export function CopyButton({ crewId }: { crewId: string }) {
  const [feedback, setFeedback] = useState<"copied" | "unavailable" | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => () => clearTimeout(timer.current), []);

  const onClick = async (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    clearTimeout(timer.current);
    try {
      const clipboard = navigator.clipboard;
      if (!clipboard?.writeText) throw new Error("Clipboard access is unavailable");
      await clipboard.writeText(crewId);
      setFeedback("copied");
    } catch {
      setFeedback("unavailable");
    }
    timer.current = setTimeout(() => setFeedback(null), CONFIRM_MS);
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
        {feedback === "copied" ? <Check aria-hidden="true" size={16} />
          : feedback === "unavailable" ? <CircleAlert aria-hidden="true" size={16} />
            : <Copy aria-hidden="true" size={16} />}
      </button>
      <span className="visually-hidden" role="status">
        {feedback === "copied" ? `Copied crew ID ${crewId}`
          : feedback === "unavailable" ? `Could not copy crew ID ${crewId}. Clipboard access is unavailable.` : ""}
      </span>
    </>
  );
}
