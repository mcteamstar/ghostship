// Port of tests/unit/test_radar_mail_subjects_client.py (TRN-370). Every assertion of
// that Python suite has a counterpart here, checked against the rendered React tree.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { App } from "../../src/App";
import { crew, callsTo, fleet, jsonResponse, mailboxes, routeFetch } from "../support/fixtures";
import { MAILBOX_ORDER } from "../../src/api/types";

const FLEET_URL = "/api/crews";
const MAIL_URL = "/api/crews/alpha/mail-history";
function historyPayload(subjects: Record<string, string[]> = {}) {
  return { capped: false, mailboxes: Object.fromEntries(
    Object.entries(mailboxes(subjects)).map(([name, entries]) => [
      name, entries.map(subject => ({ subject, sender: null, timestamp: null })),
    ]),
  ) };
}

const ROW = 'tr[data-crew-id="alpha"]';

const ESCAPED_SUBJECT = "<img src=x onerror=alert(1)> hi";

function fleetRoute(): () => Response {
  return () => jsonResponse(fleet([crew({ crew_id: "alpha", status: "running" })]));
}

/** Opens the alpha inspector and waits for its message body to settle. */
async function openAlpha(container: HTMLElement): Promise<void> {
  fireEvent.click(container.querySelector(ROW) as HTMLElement);
  await waitFor(() =>
    expect(
      screen.queryByText("Mailbox history unavailable.") ??
        container.querySelector(".history-group"),
    ).not.toBeNull(),
  );
  const recipient = screen.queryByRole("button", { name: "Recipient" });
  if (recipient) fireEvent.click(recipient);
}

async function renderAlpha(mailRoute: () => Response | Promise<Response>): Promise<{ container: HTMLElement; mock: Mock }> {
  const mock = routeFetch({ [FLEET_URL]: fleetRoute(), [MAIL_URL]: mailRoute });
  const { container } = render(<App />);
  await screen.findByText(/Refreshed at:/);
  await openAlpha(container);
  return { container, mock };
}

describe("mailbox subjects (TRN-370 client port)", () => {
  beforeEach(() => {
    document.title = "Ghostship Fleet Radar";
    // Opening a row writes #crew=<id> to the URL; a later test must not deep-link into it.
    window.location.hash = "";
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    window.location.hash = "";
  });

  describe("rendering", () => {
    const subjectsRoute = () =>
      jsonResponse(historyPayload({ ghost: [ESCAPED_SUBJECT], banshee: ["plain"] }));

    it("requests the subjects with session credentials", async () => {
      const { mock } = await renderAlpha(subjectsRoute);
      const [init] = callsTo(mock, MAIL_URL);
      expect(init?.credentials).toBe("include");
    });

    it("renders all eight mailboxes in the transport order", async () => {
      const { container } = await renderAlpha(subjectsRoute);
      const names = Array.from(container.querySelectorAll(".history-group h3")).map((n) => n.textContent?.split(" · ")[0]);
      expect(names).toEqual([...MAILBOX_ORDER]);
    });

    it("escapes subject text and never executes it", async () => {
      const { container } = await renderAlpha(subjectsRoute);
      expect(screen.getByText(ESCAPED_SUBJECT)).toBeInTheDocument();
      expect(container.querySelector("img")).toBeNull();
    });

    it("shows the explicit empty state for each empty mailbox", async () => {
      const { container } = await renderAlpha(subjectsRoute);
      expect(screen.getAllByText("No messages.")).toHaveLength(6);
      expect(screen.getByText("plain").tagName).toBe("STRONG");
      expect(container.querySelectorAll(".history-group li")).toHaveLength(2);
    });

    it("gives every mailbox its own section, with its subjects inside it", async () => {
      const { container } = await renderAlpha(subjectsRoute);
      const ghost = Array.from(container.querySelectorAll(".history-group")).find(
        (section) => section.querySelector(".history-group h3")?.textContent?.split(" · ")[0] === "ghost",
      ) as HTMLElement;
      expect(within(ghost).getByText(ESCAPED_SUBJECT)).toBeInTheDocument();
    });
  });

  describe("unavailable state", () => {
    it("shows one unavailable state on an HTTP error, and no mailbox as empty", async () => {
      const { container } = await renderAlpha(() => new Response("{}", { status: 503, headers: { "content-type": "application/json" } }));
      expect(screen.getByText("Mailbox history unavailable.")).toBeInTheDocument();
      expect(screen.queryByText("No messages.")).toBeNull();
      expect(container.querySelector(".history-group strong")).toBeNull();
    });

    it("shows the unavailable state on a network error", async () => {
      const { container } = await renderAlpha(() => {
        throw new TypeError("offline");
      });
      expect(screen.getByText("Mailbox history unavailable.")).toBeInTheDocument();
      expect(screen.queryByText("No messages.")).toBeNull();
      expect(container.querySelector(".history-group")).toBeNull();
    });

    it("shows the unavailable state for a payload without mailboxes", async () => {
      await renderAlpha(() => jsonResponse({ error: "x" }));
      expect(screen.getByText("Mailbox history unavailable.")).toBeInTheDocument();
      expect(screen.queryByText("No messages.")).toBeNull();
    });

    it("shows the unavailable state, not a partial list, when one mailbox is missing", async () => {
      const partial = historyPayload({ ghost: ["hello"] });
      delete partial.mailboxes.admiral;
      await renderAlpha(() => jsonResponse(partial));
      expect(screen.getByText("Mailbox history unavailable.")).toBeInTheDocument();
      expect(screen.queryByText("hello")).toBeNull();
    });
  });

  describe("open row survives a fleet poll", () => {
    it("keeps the fetched subjects after a fleet refresh and does not fetch them again", async () => {
      vi.useFakeTimers();
      const mock = routeFetch({
        [FLEET_URL]: fleetRoute(),
        [MAIL_URL]: () => jsonResponse(historyPayload({ banshee: ["plain"], ghost: [ESCAPED_SUBJECT] })),
      });
      const { container } = render(<App />);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      await act(async () => {
        fireEvent.click(container.querySelector(ROW) as HTMLElement);
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(screen.getByText("plain")).toBeInTheDocument();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(25_000); // a fleet refresh arrives
      });
      expect(callsTo(mock, FLEET_URL).length).toBeGreaterThan(1);
      expect(screen.getByText("plain")).toBeInTheDocument();
      expect(screen.getByText(ESCAPED_SUBJECT)).toBeInTheDocument();
      expect(callsTo(mock, MAIL_URL)).toHaveLength(1);
    });

    it("keeps the unavailable state across a fleet refresh without fetching again", async () => {
      vi.useFakeTimers();
      const mock = routeFetch({
        [FLEET_URL]: fleetRoute(),
        [MAIL_URL]: () => new Response("{}", { status: 503, headers: { "content-type": "application/json" } }),
      });
      const { container } = render(<App />);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      await act(async () => {
        fireEvent.click(container.querySelector(ROW) as HTMLElement);
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(screen.getByText("Mailbox history unavailable.")).toBeInTheDocument();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(25_000);
      });
      expect(screen.getByText("Mailbox history unavailable.")).toBeInTheDocument();
      expect(screen.queryByText("No messages.")).toBeNull();
      expect(callsTo(mock, MAIL_URL)).toHaveLength(1);
    });

    it("drops the subjects when the row is collapsed, and fetches a fresh snapshot on reopen", async () => {
      const mock = routeFetch({
        [FLEET_URL]: fleetRoute(),
        [MAIL_URL]: () => jsonResponse(historyPayload({ banshee: ["plain"] })),
      });
      const { container } = render(<App />);
      await screen.findByText(/Refreshed at:/);
      await openAlpha(container);
      expect(screen.getByText("plain")).toBeInTheDocument();

      fireEvent.click(container.querySelector(ROW) as HTMLElement); // collapse
      expect(screen.queryByText("plain")).toBeNull();

      fireEvent.click(container.querySelector(ROW) as HTMLElement); // reopen
      await waitFor(() => expect(screen.getByText("plain")).toBeInTheDocument());
      expect(callsTo(mock, MAIL_URL)).toHaveLength(2);
    });
  });

  describe("reads stay off the fleet poll", () => {
    it("requests subjects only when a row is expanded, never from a fleet refresh", async () => {
      vi.useFakeTimers();
      const mock = routeFetch({
        [FLEET_URL]: fleetRoute(),
        [MAIL_URL]: () => jsonResponse(historyPayload()),
      });
      render(<App />);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(15_000); // three scheduled fleet refreshes
      });
      expect(callsTo(mock, FLEET_URL).length).toBeGreaterThanOrEqual(3);
      expect(callsTo(mock, MAIL_URL)).toHaveLength(0);
    });
  });
});
