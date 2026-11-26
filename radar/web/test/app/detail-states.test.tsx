import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../../src/App";
import { crew, fleet, jsonResponse, mailboxes, opaqueRedirect, routeFetch } from "../support/fixtures";

const ROW = 'tr[data-crew-id="alpha"]';

type Reply = () => Response | Promise<Response>;

const ok: Reply = () => jsonResponse({ agents: [{ task_id: "live-1", agent: "ghost", done: false, elapsed_secs: 5 }] });
const okJobs: Reply = () => jsonResponse({ jobs: [{ name: "nightly-review", agent: "reaper", schedule: "every 3600s" }] });
const okMail: Reply = () => jsonResponse({ mailboxes: mailboxes({ ghost: ["Handoff: TRN-371"] }) });
const failed: Reply = () => new Response("{}", { status: 503, headers: { "content-type": "application/json" } });

/** Routes the fleet and alpha's three detail endpoints, then opens alpha. */
async function openAlpha(routes: { agents?: Reply; crons?: Reply; mail?: Reply }): Promise<HTMLElement> {
  routeFetch({
    "/api/crews": () => jsonResponse(fleet([crew({ crew_id: "alpha", status: "running" })])),
    "/api/crews/alpha/agents": routes.agents ?? ok,
    "/crews/alpha/api/crons": routes.crons ?? okJobs,
    "/api/crews/alpha/mail-subjects": routes.mail ?? okMail,
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

describe("scheduled jobs states (6.7)", () => {
  it("shows a loading state until the scheduled jobs answer", async () => {
    await openAlpha({ crons: () => new Promise<Response>(() => {}) });
    expect(screen.getByText("Loading scheduled jobs…")).toBeInTheDocument();
  });

  it("shows an unavailable state, never an empty list, when the scheduled jobs request fails", async () => {
    await openAlpha({ crons: failed });
    await waitFor(() => expect(screen.getByText("Scheduled jobs unavailable.")).toBeInTheDocument());
    expect(screen.queryByText("No scheduled jobs.")).toBeNull();
  });

  it("shows the empty state, not the unavailable one, when the crew has no jobs", async () => {
    await openAlpha({ crons: () => jsonResponse({ jobs: [] }) });
    await waitFor(() => expect(screen.getByText("No scheduled jobs.")).toBeInTheDocument());
    expect(screen.queryByText("Scheduled jobs unavailable.")).toBeNull();
  });

  it("shows the session-expired note when the scheduled jobs request is redirected to sign-in", async () => {
    await openAlpha({ crons: () => opaqueRedirect() });
    await waitFor(() => expect(screen.getByText("Session expired, sign in again")).toBeInTheDocument());
  });

  it("leaves the other sections unchanged when one section fails", async () => {
    await openAlpha({ crons: failed });
    await waitFor(() => expect(screen.getByText("Scheduled jobs unavailable.")).toBeInTheDocument());
    expect(screen.getByText("live-1")).toBeInTheDocument();
    expect(screen.getByText("Handoff: TRN-371")).toBeInTheDocument();
    expect(screen.getByText("Credentials")).toBeInTheDocument();
  });
});

describe("mailbox subjects states (6.7)", () => {
  it("shows a loading state until the mailbox subjects answer", async () => {
    await openAlpha({ mail: () => new Promise<Response>(() => {}) });
    expect(screen.getByText("Loading mailbox subjects…")).toBeInTheDocument();
  });

  it("shows the session-expired note, not the unavailable state, when the mailbox request is redirected", async () => {
    await openAlpha({ mail: () => opaqueRedirect() });
    await waitFor(() => expect(screen.getByText("Session expired, sign in again")).toBeInTheDocument());
    expect(screen.queryByText("Mailbox subjects unavailable.")).toBeNull();
  });

  it("keeps the agent list and the jobs when only the mailbox request fails", async () => {
    await openAlpha({ mail: failed });
    await waitFor(() => expect(screen.getByText("Mailbox subjects unavailable.")).toBeInTheDocument());
    expect(screen.getByText("live-1")).toBeInTheDocument();
    expect(screen.getByText("nightly-review")).toBeInTheDocument();
  });
});
