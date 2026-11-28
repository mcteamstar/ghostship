import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../../src/App";
import { crew, fleet, jsonResponse, mailboxes, routeFetch } from "../support/fixtures";

function historyPayload(subjects: Record<string, string[]> = {}) {
  return { capped: false, mailboxes: Object.fromEntries(
    Object.entries(mailboxes(subjects)).map(([name, entries]) => [
      name, entries.map(subject => ({ subject, sender: null, timestamp: null })),
    ]),
  ) };
}

const ROW = 'tr[data-crew-id="alpha"]';

/** Routes the fleet and alpha's mailbox subjects, then opens alpha. */
async function openMailboxes(payload: Record<string, string[]>): Promise<HTMLElement> {
  routeFetch({
    "/api/crews": () => jsonResponse(fleet([crew({ crew_id: "alpha" })])),
    "/api/crews/alpha/mail-history": () => jsonResponse(historyPayload(payload)),
  });
  const { container } = render(<App />);
  await screen.findByText(/Refreshed at:/);
  fireEvent.click(container.querySelector(ROW) as HTMLElement);
  await waitFor(() => expect(container.querySelector(".history-group")).not.toBeNull());
  fireEvent.click(screen.getByRole("button", { name: "Recipient" }));
  return container;
}

function sectionFor(container: HTMLElement, name: string): HTMLElement {
  const section = Array.from(container.querySelectorAll<HTMLElement>(".history-group")).find(
    (candidate) => candidate.querySelector(".history-group h3")?.textContent?.split(" · ")[0] === name,
  );
  if (!section) throw new Error(`no section for ${name}`);
  return section;
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = "";
});

describe("mailbox history view (6.6)", () => {
  it("shows one section per mailbox, in order, with the mailbox name and its count", async () => {
    const container = await openMailboxes({ ghost: ["a", "b"], captain: ["c"] });
    const names = Array.from(container.querySelectorAll(".history-group h3")).map((n) => n.textContent?.split(" · ")[0]);
    expect(names).toEqual(["ghost", "spectre", "banshee", "wraith", "reaper", "raven", "captain", "admiral"]);
    expect(sectionFor(container, "ghost").querySelector("small")).toHaveTextContent("2");
    expect(sectionFor(container, "captain").querySelector("small")).toHaveTextContent("1");
    expect(sectionFor(container, "spectre").querySelector("small")).toHaveTextContent("0");
  });

  it("shows a 200-character subject in full", async () => {
    const long = "Review requested: ".padEnd(200, "x");
    const container = await openMailboxes({ ghost: [long] });
    const item = screen.getByText(long);
    expect(item.tagName).toBe("STRONG");
    expect(item.textContent).toHaveLength(200);
    expect(container.querySelector("ul")).toBeInTheDocument();
  });

  it("shows No messages. for an empty mailbox", async () => {
    const container = await openMailboxes({ ghost: ["a"] });
    expect(sectionFor(container, "spectre").textContent).toContain("No messages.");
    expect(sectionFor(container, "spectre").querySelector("ul")).toBeNull();
  });

  it("renders only the mailbox name, its count and the subject text", async () => {
    const container = await openMailboxes({ ghost: ["Handoff", "Check-in"] });
    expect(sectionFor(container, "ghost")).toHaveTextContent("Unknown sender → ghost");
    expect(sectionFor(container, "ghost")).toHaveTextContent("Handoff");
  });
});
