import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../../src/App";
import { crew, fleet, jsonResponse, mailboxes, opaqueRedirect, routeFetch } from "../support/fixtures";

function historyPayload(subjects: Record<string, string[]> = {}) {
  return { capped: false, mailboxes: Object.fromEntries(
    Object.entries(mailboxes(subjects)).map(([name, entries]) => [
      name, entries.map(subject => ({ subject, sender: null, timestamp: null })),
    ]),
  ) };
}

const ROW = 'tr[data-crew-id="alpha"]';

type Reply = () => Response | Promise<Response>;

const ok: Reply = () => jsonResponse({ agents: [{ task_id: "live-1", agent: "ghost", done: false, elapsed_secs: 5 }] });
const okMail: Reply = () => jsonResponse(historyPayload({ ghost: ["Handoff: TRN-371"] }));
const failed: Reply = () => new Response("{}", { status: 503, headers: { "content-type": "application/json" } });

/** Routes the fleet and alpha's two detail endpoints, then opens alpha. */
async function openAlpha(routes: { agents?: Reply; mail?: Reply }): Promise<HTMLElement> {
  routeFetch({
    "/api/crews": () => jsonResponse(fleet([crew({ crew_id: "alpha", status: "running" })])),
    "/api/crews/alpha/agents": routes.agents ?? ok,
    "/api/crews/alpha/mail-history": routes.mail ?? okMail,
  });
  const { container } = render(<App />);
  await screen.findByText(/Refreshed at:/);
  fireEvent.click(container.querySelector(ROW) as HTMLElement);
  return container;
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = "";
});

describe("mailbox subjects states (6.7)", () => {
  it("shows a loading state until the mailbox subjects answer", async () => {
    await openAlpha({ mail: () => new Promise<Response>(() => {}) });
    expect(screen.getByText("Loading mailbox history…")).toBeInTheDocument();
  });

  it("shows the session-expired note, not the unavailable state, when the mailbox request is redirected", async () => {
    await openAlpha({ mail: () => opaqueRedirect() });
    await waitFor(() => expect(screen.getByText("Session expired, sign in again")).toBeInTheDocument());
    expect(screen.queryByText("Mailbox history unavailable.")).toBeNull();
  });

  it("keeps the agent list when only the mailbox request fails", async () => {
    await openAlpha({ mail: failed });
    await waitFor(() => expect(screen.getByText("Mailbox history unavailable.")).toBeInTheDocument());
    expect(await screen.findByText("live-1")).toBeInTheDocument();
  });
});

describe("one section fails and the others keep their data", () => {
  it("keeps the mailbox subjects and the credentials when only the agents request fails", async () => {
    await openAlpha({ agents: failed });
    expect(await screen.findByText("Handoff: TRN-371")).toBeInTheDocument();
    expect(await screen.findByText("Active tasks unavailable.")).toBeInTheDocument();
    expect(screen.getByText("Credentials")).toBeInTheDocument();
  });

  it("shows an unavailable state, not a session expiry, when the agents request answers an empty 200", async () => {
    await openAlpha({ agents: () => new Response(null, { status: 200 }) });
    await waitFor(() => expect(screen.getByText("Active tasks unavailable.")).toBeInTheDocument());
    expect(screen.queryByText("Session expired, sign in again")).toBeNull();
  });
});
