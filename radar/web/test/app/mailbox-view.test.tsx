import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../../src/App";
import { crew, fleet, jsonResponse, mailboxes, routeFetch } from "../support/fixtures";

const ROW = 'tr[data-crew-id="alpha"]';

/** Routes the fleet and alpha's mailbox subjects, then opens alpha. */
async function openMailboxes(payload: Record<string, string[]>): Promise<HTMLElement> {
  routeFetch({
    "/api/crews": () => jsonResponse(fleet([crew({ crew_id: "alpha" })])),
    "/api/crews/alpha/mail-subjects": () => jsonResponse({ mailboxes: mailboxes(payload) }),
  });
  const { container } = render(<App />);
  await screen.findByText(/Refreshed at:/);
  fireEvent.click(container.querySelector(ROW) as HTMLElement);
  await waitFor(() => expect(container.querySelector(".mail-mailbox")).not.toBeNull());
  return container;
}

function sectionFor(container: HTMLElement, name: string): HTMLElement {
  const section = Array.from(container.querySelectorAll<HTMLElement>(".mail-mailbox")).find(
    (candidate) => candidate.querySelector(".mail-mailbox-name")?.textContent === name,
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
    const names = Array.from(container.querySelectorAll(".mail-mailbox-name")).map((n) => n.textContent);
    expect(names).toEqual(["ghost", "spectre", "banshee", "wraith", "reaper", "raven", "captain", "admiral"]);
    expect(sectionFor(container, "ghost").querySelector(".mail-count")).toHaveTextContent("2");
    expect(sectionFor(container, "captain").querySelector(".mail-count")).toHaveTextContent("1");
    expect(sectionFor(container, "spectre").querySelector(".mail-count")).toHaveTextContent("0");
  });

  it("shows a 200-character subject in full", async () => {
    const long = "Review requested: ".padEnd(200, "x");
    const container = await openMailboxes({ ghost: [long] });
    const item = screen.getByText(long);
    expect(item.tagName).toBe("LI");
    expect(item.textContent).toHaveLength(200);
    expect(container.querySelector(".mail-subjects")).toBeInTheDocument();
  });

  it("shows No messages. for an empty mailbox", async () => {
    const container = await openMailboxes({ ghost: ["a"] });
    expect(sectionFor(container, "spectre").textContent).toContain("No messages.");
    expect(sectionFor(container, "spectre").querySelector(".mail-subjects")).toBeNull();
  });

  it("renders only the mailbox name, its count and the subject text", async () => {
    const container = await openMailboxes({ ghost: ["Handoff", "Check-in"] });
    expect(sectionFor(container, "ghost").textContent).toBe("ghost2HandoffCheck-in");
  });
});
