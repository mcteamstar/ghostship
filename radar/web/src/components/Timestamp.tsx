import { relativeTime } from "../format";

/** A relative time with the full timestamp as its tooltip. A missing or invalid date is an em dash. */
export function Timestamp({ iso }: { iso: string | null | undefined }) {
  const text = relativeTime(iso, Date.now());
  if (text === null) return <>—</>;
  return <span title={iso ?? undefined}>{text}</span>;
}
