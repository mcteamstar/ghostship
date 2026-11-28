import { useState } from "react";
import { getJson, RequestError } from "../../api/request";
import { MAILBOX_ORDER, PERSONA_AGENTS } from "../../api/types";
import { FailedSection } from "./states";
import { useSnapshot } from "../../detail/useSnapshot";
import { SnapshotControls } from "./SnapshotControls";

type Delivery = { subject: string | null; sender: string | null; timestamp: string | null };
type Snapshot = { mailboxes: Record<string, Delivery[]>; capped: boolean };
type Group = "Time" | "Sender" | "Recipient";

const shortSenders = new Set<string>([...PERSONA_AGENTS, "captain", "admiral"]);

function senderLabel(sender: string | null): string {
  if (!sender) return "Unknown sender";
  const local = /^([^+@]+)(?:\+[^@]+)?@localhost$/i.exec(sender)?.[1].toLowerCase();
  return local && shortSenders.has(local) ? local : sender;
}

function Sender({ address }: { address: string | null }) {
  const label = senderLabel(address);
  if (!address || address === label) return <span>{label}</span>;
  return <details className="history-sender">
    <summary aria-label={`${label} sender address`}>{label}</summary>
    <span>{address}</span>
  </details>;
}

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

async function readHistory(crewId: string, signal: AbortSignal) {
  return readSnapshot(await getJson<unknown>(`/api/crews/${encodeURIComponent(crewId)}/mail-history`, { signal }));
}

export function MailHistory({ crewId }: { crewId: string }) {
  const [group, setGroup] = useState<Group>("Time");
  const [query, setQuery] = useState("");
  const { snapshot, error, pending, refresh } = useSnapshot(crewId, readHistory);
  const controls = <SnapshotControls label="mailbox history" receivedAt={snapshot?.receivedAt}
    refresh={refresh} pending={pending} failed={!!error} />;
  const failure = error && <FailedSection error={error} unavailable={snapshot
    ? "Could not refresh mailbox history. Showing the last successful snapshot."
    : "Mailbox history unavailable."} />;
  if (!snapshot) return <>{failure || <p role="status">Loading mailbox history…</p>}{controls}</>;

  const date = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });
  const clock = new Intl.DateTimeFormat(undefined, { timeStyle: "short" });
  const rows = MAILBOX_ORDER.flatMap(recipient =>
    snapshot.data.mailboxes[recipient].map((item, index) => ({
      ...item, recipient, id: `${recipient}-${index}`, time: timestamp(item.timestamp),
    })));
  rows.sort((a, b) => (b.time ?? -Infinity) - (a.time ?? -Infinity));
  const needle = query.trim().toLowerCase();
  const matches = needle ? rows.filter(row =>
    [row.subject, row.sender, senderLabel(row.sender), row.recipient].some(
      value => value?.toLowerCase().includes(needle),
    )) : rows;
  const groups = new Map<string | null, typeof rows>();
  if (group === "Recipient" && !needle) MAILBOX_ORDER.forEach(name => groups.set(name, []));
  for (const row of matches) {
    const name = group === "Recipient" ? row.recipient : group === "Sender"
      ? row.sender || null : row.time === null ? null : date.format(row.time);
    const items = groups.get(name);
    if (items) items.push(row);
    else groups.set(name, [row]);
  }

  return <section aria-label="Mailbox history">
    {controls}
    {failure}
    <div className="radar-controls history-search">
      <input type="search" className="fleet-filter" aria-label="Search retained messages"
        placeholder="Search retained messages…" value={query} onChange={event => setQuery(event.target.value)} />
      {query && <button type="button" onClick={event => {
        event.currentTarget.parentElement?.querySelector("input")?.focus();
        setQuery("");
      }}>Clear search</button>}
    </div>
    <div className="radar-controls" role="group" aria-label="Group mailbox history by">
      <span>Group by</span>
      {(["Time", "Sender", "Recipient"] as const).map(name =>
        <button key={name} aria-pressed={group === name} onClick={() => setGroup(name)}>{name}</button>)}
    </div>
    {snapshot.data.capped && <p className="state">Showing the latest retained deliveries, up to 50 per mailbox.</p>}
    <p className="state" role="status">{needle && rows.length
      ? matches.length ? `${matches.length} of ${rows.length} deliveries match.` : "No matching deliveries."
      : !rows.length ? "No messages." : ""}</p>
    {[...groups].map(([name, items]) => <section key={name === null ? "missing" : `value:${name}`} className="history-group">
      <h3>{group === "Sender" ? senderLabel(name) : name ?? "Undated deliveries"}
        {group !== "Time" && <small> · {items.length}</small>}</h3>
      {group === "Sender" && name && senderLabel(name) !== name && <p className="state history-address">{name}</p>}
      {items.length ? <ul>{items.map(row => <li key={row.id}>
        <strong>{row.subject || "(No subject)"}</strong>
        <div className="history-meta">
          <div className="history-participants"><Sender address={row.sender} />{" "}<span>→ {row.recipient}</span></div>
          <small>{row.time === null ? group !== "Time" && "Undated" : <time dateTime={row.timestamp ?? undefined}>
            {group !== "Time" && `${date.format(row.time)} · `}{clock.format(row.time)}
          </time>}</small>
        </div>
      </li>)}</ul> : <p className="state">No messages.</p>}
    </section>)}
  </section>;
}
