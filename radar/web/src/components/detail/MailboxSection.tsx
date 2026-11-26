import { useId } from "react";
import { MAILBOX_ORDER, type MailSubjectsPayload } from "../../api/types";
import type { Section } from "../../detail/useCrewDetail";
import { FailedSection } from "./states";

/**
 * Subject lines for each of the eight mailboxes, in the transport's order. Each mailbox
 * shows its name and how many subjects it has. A failed read is one unavailable state for
 * the whole crew, never a partial list.
 */
export function MailboxSection({ detail }: { detail: Section<MailSubjectsPayload> }) {
  return (
    <>
      <h2 className="detail-section">Mailbox subjects</h2>
      {detail.state === "ok" ? (
        <MailList mailboxes={detail.data.mailboxes} />
      ) : detail.state === "failed" ? (
        <FailedSection error={detail.error} unavailable="Mailbox subjects unavailable." />
      ) : (
        <p className="state">Loading mailbox subjects…</p>
      )}
    </>
  );
}

function MailList({ mailboxes }: { mailboxes: MailSubjectsPayload["mailboxes"] }) {
  const base = useId();
  return (
    <div className="mail-list">
      {MAILBOX_ORDER.map((name) => {
        const subjects = mailboxes[name] ?? [];
        const headingId = `${base}-${name}`;
        return (
          <section className="mail-mailbox" aria-labelledby={headingId} key={name}>
            <p className="mail-mailbox-head" id={headingId}>
              <strong className="mail-mailbox-name">{name}</strong>
              <span className="mail-count">{subjects.length}</span>
            </p>
            {subjects.length === 0 ? (
              <p className="state">No messages.</p>
            ) : (
              <ul className="mail-subjects">
                {subjects.map((subject, index) => (
                  <li key={index}>{subject}</li>
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}
