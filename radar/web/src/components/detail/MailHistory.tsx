import { useEffect, useState } from "react";
import { getJson, RequestError, toRequestError } from "../../api/request";
import { MAILBOX_ORDER } from "../../api/types";
import { FailedSection } from "./states";

type Delivery = { subject: string | null; sender: string | null; timestamp: string | null };
type Snapshot = { mailboxes: Record<string, Delivery[]>; capped: boolean };
type Group = "Time" | "Sender" | "Recipient";
type Result = { data: Snapshot } | { error: RequestError };

function readSnapshot(value: unknown): Snapshot {
  if (!value || typeof value !== "object") throw new RequestError("http-error", "Invalid mailbox history");
  const data = value as Snapshot;
  if (typeof data.capped !== "boolean" || !data.mailboxes ||
    !MAILBOX_ORDER.every(name => Array.isArray(data.mailboxes[name]) && data.mailboxes[name].every(row =>
      row && ["subject", "sender", "timestamp"].every(key =>
        row[key as keyof Delivery] === null || typeof row[key as keyof Delivery] === "string")))) {
    throw new RequestError("http-error", "Invalid mailbox history");
  }
  return data;
}

function timestamp(value: string | null) {
  if (!value) return null;
  const time = Date.parse(value);
  return Number.isFinite(time) ? time : null;
}

export function MailHistory({ crewId }: { crewId: string }) {
  const [group, setGroup] = useState<Group>("Time");
  const [result, setResult] = useState<Result>();
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void getJson<unknown>(`/api/crews/${encodeURIComponent(crewId)}/mail-history`, {
      signal: controller.signal,
    }).then(readSnapshot).then(
      data => { if (!controller.signal.aborted) setResult({ data }); },
      error => { if (!controller.signal.aborted) setResult({ error: toRequestError(error) }); },
    );
    return () => controller.abort();
  }, [crewId, attempt]);

  if (!result) return <p role="status">Loading mailbox history…</p>;
  if ("error" in result) return <>
    <FailedSection error={result.error} unavailable="Mailbox history unavailable." />
    <button className="radar-action" onClick={() => {
      setResult(undefined);
      setAttempt(value => value + 1);
    }}>Retry mailbox history</button>
  </>;

  const date = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });
  const clock = new Intl.DateTimeFormat(undefined, { timeStyle: "short" });
  const rows = MAILBOX_ORDER.flatMap(recipient =>
    result.data.mailboxes[recipient].map((item, index) => ({
      ...item, recipient, id: `${recipient}-${index}`, time: timestamp(item.timestamp),
    })));
  rows.sort((a, b) => (b.time ?? -Infinity) - (a.time ?? -Infinity));
  const groups = new Map<string, typeof rows>();
  if (group === "Recipient") MAILBOX_ORDER.forEach(name => groups.set(name, []));
  for (const row of rows) {
    const name = group === "Recipient" ? row.recipient : group === "Sender"
      ? row.sender || "Unknown sender" : row.time === null ? "Unknown date" : date.format(row.time);
    const items = groups.get(name);
    if (items) items.push(row);
    else groups.set(name, [row]);
  }

  return <section aria-label="Mailbox history">
    <div className="radar-controls" role="group" aria-label="Group mailbox history by">
      <span>Group by</span>
      {(["Time", "Sender", "Recipient"] as const).map(name =>
        <button key={name} aria-pressed={group === name} onClick={() => setGroup(name)}>{name}</button>)}
    </div>
    {result.data.capped && <p className="state">Showing the latest retained deliveries, up to 50 per mailbox.</p>}
    {!rows.length && group !== "Recipient" && <p>No messages.</p>}
    {[...groups].map(([name, items]) => <section key={name} className="history-group">
      <h3>{name}{group !== "Time" && <small> · {items.length}</small>}</h3>
      {items.length ? <ul>{items.map(row => <li key={row.id}>
        <small>{row.time === null ? "Unknown time" : group === "Time"
          ? clock.format(row.time) : `${date.format(row.time)} · ${clock.format(row.time)}`}</small>
        <div><span>{row.sender || "Unknown sender"} → {row.recipient}</span>
          <strong>{row.subject || "(No subject)"}</strong></div>
      </li>)}</ul> : <p className="state">No messages.</p>}
    </section>)}
  </section>;
}
