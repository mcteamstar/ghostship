import { ArrowDownToLine, Search, X } from "lucide-react";
import { useId, useRef, useState } from "react";
import { getJson, RequestError } from "../../api/request";
import { MAILBOX_ORDER, PERSONA_AGENTS } from "../../api/types";
import { FailedSection } from "./states";
import { useSnapshot } from "../../detail/useSnapshot";
import { SnapshotControls } from "./SnapshotControls";

type Delivery = { subject: string | null; sender: string | null; timestamp: string | null };
type Snapshot = { mailboxes: Record<string, Delivery[]>; capped: boolean };
type Group = "Time" | "Sender" | "Recipient";
type Mailbox = typeof MAILBOX_ORDER[number];
const jumpTarget = { Time: "date", Sender: "sender", Recipient: "mailbox" } as const;
const date = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });
const clock = new Intl.DateTimeFormat(undefined, { timeStyle: "short" });

const shortSenders = new Set<string>([...PERSONA_AGENTS, "captain", "admiral"]);

function senderLabel(sender: string | null): string {
  if (!sender) return "Unknown sender";
  const local = /^([^+@]+)(?:\+[^@]+)?@localhost$/i.exec(sender)?.[1].toLowerCase();
  return local && shortSenders.has(local) ? local : sender;
}

function groupLabel(name: string | null, group: Group) {
  return group === "Sender" ? senderLabel(name) : name ?? "Undated deliveries";
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
  const [mailbox, setMailbox] = useState<Mailbox | "">("");
  const [jump, setJump] = useState("");
  const search = useRef<HTMLInputElement>(null);
  const results = useRef<HTMLDivElement>(null);
  const mailboxId = useId();
  const groupId = useId();

  function resetScroll() {
    setJump("");
    if (results.current) results.current.scrollTop = 0;
  }

  function clearFilters() {
    setQuery("");
    setMailbox("");
    resetScroll();
    search.current?.focus();
  }
  const { snapshot, error, pending, refresh } = useSnapshot(crewId, readHistory);
  const controls = <SnapshotControls label="mailbox history" receivedAt={snapshot?.receivedAt}
    refresh={refresh} pending={pending} failed={!!error} />;
  const failure = error && <FailedSection error={error} unavailable={snapshot
    ? "Could not refresh mailbox history. Showing the last successful snapshot."
    : "Mailbox history unavailable."} />;
  if (!snapshot) return <div className="history-load-state">
    {failure || <p className="state" role="status">Loading mailbox history…</p>}
    {controls}
  </div>;

  const rows = MAILBOX_ORDER.flatMap(recipient =>
    snapshot.data.mailboxes[recipient].map((item, index) => ({
      ...item, recipient, id: `${recipient}-${index}`, time: timestamp(item.timestamp),
    })));
  rows.sort((a, b) => (b.time ?? -Infinity) - (a.time ?? -Infinity));
  const needle = query.trim().toLowerCase();
  const restricted = !!(needle || mailbox);
  const matches = rows.filter(row => (!mailbox || row.recipient === mailbox) &&
    (!needle || [row.subject, row.sender, senderLabel(row.sender), row.recipient].some(
      value => value?.toLowerCase().includes(needle),
    )));
  const groups = new Map<string | null, typeof rows>();
  if (group === "Recipient" && !restricted) MAILBOX_ORDER.forEach(name => groups.set(name, []));
  for (const row of matches) {
    const name = group === "Recipient" ? row.recipient : group === "Sender"
      ? row.sender || null : row.time === null ? null : date.format(row.time);
    const items = groups.get(name);
    if (items) items.push(row);
    else groups.set(name, [row]);
  }
  const sections = [...groups].map(([name, items], index) => ({
    name, items, id: `${groupId}-${index}`, key: JSON.stringify(name),
  }));
  const destinations = sections.filter(section => section.items.length);
  const destination = destinations.find(section => section.key === jump);
  const count = restricted ? `${matches.length} of ${rows.length} deliveries`
    : `${rows.length} ${rows.length === 1 ? "delivery" : "deliveries"}`;

  return <section className="mail-history" aria-label="Mailbox history">
    <div className="history-toolbar">
      <div className="history-query">
        <div className="history-search">
          <Search size={16} aria-hidden="true" />
          <input ref={search} type="search" className="fleet-filter" aria-label="Search retained messages"
            placeholder="Search messages…" value={query} onChange={event => {
              setQuery(event.target.value);
              resetScroll();
            }} />
          {query && <button className="radar-icon-action clear-mail-search" type="button" title="Clear search"
            aria-label="Clear search" onClick={() => {
              setQuery("");
              resetScroll();
              search.current?.focus();
            }}><X size={15} aria-hidden="true" /></button>}
        </div>
        <div className="mailbox-scope">
          <label className="visually-hidden" htmlFor={mailboxId}>Receiving mailbox</label>
          <select id={mailboxId} value={mailbox} onChange={event => {
            const value = MAILBOX_ORDER.find(name => name === event.target.value);
            setMailbox(value ?? "");
            resetScroll();
          }}>
            <option value="">All mailboxes</option>
            {MAILBOX_ORDER.map(name => <option key={name} value={name}>To: {name}</option>)}
          </select>
        </div>
      </div>
      <div className="history-options">
        <div className="radar-controls history-grouping">
          <span>Group by</span>
          <div className="radar-controls segmented-control" role="group" aria-label="Group mailbox history by">
            {(["Time", "Sender", "Recipient"] as const).map(name =>
              <button type="button" key={name} aria-pressed={group === name} onClick={() => {
                setGroup(name);
                resetScroll();
              }}>{name}</button>)}
          </div>
        </div>
        {controls}
      </div>
      {failure}
      <div className="history-summary">
        <div>
          <p className="state" role="status">{count}</p>
          {snapshot.data.capped && <p className="state">Showing up to 50 per mailbox</p>}
        </div>
        {destinations.length > 1 && <form className="history-jump" onSubmit={event => {
          event.preventDefault();
          if (!destination) return;
          const section = document.getElementById(destination.id);
          section?.scrollIntoView?.({ block: "start" });
          section?.querySelector("h3")?.focus({ preventScroll: true });
        }}>
          <select aria-label={`Jump to ${jumpTarget[group]}`} value={destination?.key ?? ""}
            onChange={event => setJump(event.target.value)}>
            <option value="">Jump to {jumpTarget[group]}…</option>
            {destinations.map(({ name, key }) =>
              <option key={key} value={key}>
                {group === "Sender" ? name || "Unknown sender" : groupLabel(name, group)}
              </option>)}
          </select>
          <button className="radar-icon-action" type="submit" disabled={!destination} aria-label="Go to message group" title="Go to message group">
            <ArrowDownToLine size={15} aria-hidden="true" />
          </button>
        </form>}
      </div>
    </div>
    <div className="history-results" ref={results}>
      {!matches.length && (group !== "Recipient" || restricted) && <div className="history-empty">
        <p>{!rows.length ? "No messages." : "No matching deliveries."}</p>
        {restricted && <button type="button" className="radar-action" onClick={clearFilters}>Clear message filters</button>}
      </div>}
      {sections.map(({ name, items, id, key }) => <section id={id} key={key} className="history-group">
        <h3 tabIndex={-1}>{groupLabel(name, group)}
          {group !== "Time" && <small> · {items.length}</small>}</h3>
        {group === "Sender" && name && senderLabel(name) !== name && <p className="state history-address">{name}</p>}
        {items.length ? <ul>{items.map(row => <li key={row.id}>
          <strong>{row.subject || "(No subject)"}</strong>
          <div className="history-meta">
            <div className="history-participants"><Sender address={row.sender} />{" "}<span>→ {row.recipient}</span></div>
            {row.time === null ? group !== "Time" && <small>Undated</small> : <small><time dateTime={row.timestamp ?? undefined}>
              {group !== "Time" && `${date.format(row.time)} · `}{clock.format(row.time)}
            </time></small>}
          </div>
        </li>)}</ul> : <p className="state history-empty-group">No messages.</p>}
      </section>)}
    </div>
  </section>;
}
