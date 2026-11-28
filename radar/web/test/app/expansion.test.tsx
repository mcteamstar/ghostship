import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { App } from "../../src/App";
import { crew, callsTo, fleet, jsonResponse, mailboxes, routeFetch } from "../support/fixtures";

const FLEET_URL = "/api/crews";
const AGENTS_URL = "/api/crews/alpha/agents";
const MAIL_URL = "/api/crews/alpha/mail-history";
const ROW_ALPHA = 'tr[data-crew-id="alpha"]';

const liveAgents = () =>
  jsonResponse({ agents: [{ task_id: "live-task-1", agent: "ghost", done: false, elapsed_secs: 47 }] });
const mailSubjects = () => jsonResponse({ capped: false, mailboxes: Object.fromEntries(Object.entries(mailboxes({ ghost: ["Handoff: TRN-371"] })).map(([name, subjects]) => [name, subjects.map(subject => ({ subject, sender: null, timestamp: null }))])) });

/** Requests under /crews/, the crew proxy path. No Radar section reads it any more. */
function crewProxyCalls(mock: Mock): unknown[] {
  return mock.mock.calls.map((call) => call[0]).filter((url) => String(url).startsWith("/crews/"));
}

/** Routes the fleet and every listed crew's detail endpoints. `overrides` replaces alpha's. */
function renderWith(overrides: Record<string, () => Response> = {}, fleetCrews = [crew({ crew_id: "alpha" })]) {
  const routes: Record<string, () => Response> = { [FLEET_URL]: () => jsonResponse(fleet(fleetCrews)) };
  for (const { crew_id: id } of fleetCrews) {
    routes[`/api/crews/${id}/agents`] = liveAgents;
    routes[`/api/crews/${id}/mail-history`] = mailSubjects;
  }
  Object.assign(routes, overrides);
  const mock = routeFetch(routes);
  return { mock };
}

describe("row expansion, deep link and copy (4.3 and 4.5)", () => {
  beforeEach(() => {
    window.location.hash = "";
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    window.location.hash = "";
  });

  it("expands a crew with its live detail and records the crew in the URL", async () => {
    renderWith();
    const { container } = render(<App />);
    await screen.findByText(/Refreshed at:/);
    const row = container.querySelector(ROW_ALPHA) as HTMLElement;
    expect(row.querySelector("button.expand-btn")).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(row);
    expect(row.querySelector("button.expand-btn")).toHaveAttribute("aria-expanded", "true");
    expect(window.location.hash).toBe("#crew=alpha");
    await waitFor(() => expect(screen.getByText("live-task-1")).toBeInTheDocument());
    expect(await screen.findByText("Handoff: TRN-371")).toBeInTheDocument();
  });

  it("collapses on a second click and clears the crew from the URL", async () => {
    renderWith();
    const { container } = render(<App />);
    await screen.findByText(/Refreshed at:/);
    const row = container.querySelector(ROW_ALPHA) as HTMLElement;
    fireEvent.click(row);
    fireEvent.click(row);
    expect(row.querySelector("button.expand-btn")).toHaveAttribute("aria-expanded", "false");
    expect(window.location.hash).toBe("");
    expect(screen.queryByRole("complementary", { name: "Crew details" })).toBeNull();
  });

  it("opens the crew named in the deep link after the first load, with its detail requests", async () => {
    window.location.hash = "#crew=beta";
    const { mock } = renderWith({}, [crew({ crew_id: "alpha" }), crew({ crew_id: "beta" })]);
    mock.mockClear();
    const { container } = render(<App />);
    await screen.findByText(/Refreshed at:/);
    await waitFor(() => expect(container.querySelector('tr[data-crew-id="beta"]')).toHaveClass("selected"));
    expect(container.querySelector('tr[data-crew-id="alpha"]')).not.toHaveClass("selected");
    await screen.findByText("Handoff: TRN-371");
    expect(callsTo(mock, "/api/crews/beta/mail-history")).toHaveLength(1);
  });

  it("ignores a deep link to a crew that is not listed", async () => {
    window.location.hash = "#crew=ghost-crew";
    renderWith();
    const { container } = render(<App />);
    await screen.findByText(/Refreshed at:/);
    expect(container.querySelector("tr.data-row.selected")).toBeNull();
  });

  it("keeps open details stable across a fleet refresh without repeating their requests", async () => {
    vi.useFakeTimers();
    const { mock } = renderWith();
    const { container } = render(<App />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    await act(async () => {
      fireEvent.click(container.querySelector(ROW_ALPHA) as HTMLElement);
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText("live-task-1")).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(25_000);
    });
    expect(callsTo(mock, FLEET_URL).length).toBeGreaterThan(1);
    expect(container.querySelector(ROW_ALPHA)).toHaveClass("selected");
    expect(screen.getByText("live-task-1")).toBeInTheDocument();
    expect(callsTo(mock, AGENTS_URL)).toHaveLength(1);
    expect(callsTo(mock, MAIL_URL)).toHaveLength(1);
    expect(crewProxyCalls(mock)).toHaveLength(0);
  });

  it("keeps the same detail DOM across a fleet refresh (no re-mount of the open panel)", async () => {
    vi.useFakeTimers();
    renderWith();
    const { container } = render(<App />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    await act(async () => {
      fireEvent.click(container.querySelector(ROW_ALPHA) as HTMLElement);
      await vi.advanceTimersByTimeAsync(0);
    });
    const panel = screen.getByText("Credentials");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(25_000);
    });
    expect(screen.getByText("Credentials")).toBe(panel);
  });

  it("copies the crew ID from the copy control and does not expand the row", async () => {
    // userEvent.setup() installs its own clipboard stub, so the mock is defined after it.
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    renderWith();
    const { container } = render(<App />);
    await screen.findByText(/Refreshed at:/);
    const copy = screen.getByRole("button", { name: "Copy crew ID alpha" });
    // A native button: browsers turn Enter and Space on it into the same click.
    expect(copy.tagName).toBe("BUTTON");
    await user.click(copy);
    expect(writeText).toHaveBeenCalledWith("alpha");
    expect(await screen.findByText("Copied crew ID alpha")).toBeInTheDocument();
    expect(container.querySelector(ROW_ALPHA)).not.toHaveClass("selected");
    expect(window.location.hash).toBe("");
    Reflect.deleteProperty(navigator, "clipboard");
  });

  it("copies on click, confirms for a moment, and does not toggle the row", async () => {
    vi.useFakeTimers();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    renderWith();
    const { container } = render(<App />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    const copy = container.querySelector(`${ROW_ALPHA} .copy-btn`) as HTMLElement;
    fireEvent.click(copy);
    expect(writeText).toHaveBeenCalledWith("alpha");
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByText("Copied crew ID alpha")).toBeInTheDocument();
    expect(container.querySelector(ROW_ALPHA)).not.toHaveClass("selected");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_500);
    });
    expect(screen.queryByText("Copied crew ID alpha")).toBeNull();
    Reflect.deleteProperty(navigator, "clipboard");
  });

  it("announces when the clipboard is unavailable instead of claiming success", async () => {
    Reflect.deleteProperty(navigator, "clipboard");
    renderWith();
    const { container } = render(<App />);
    await screen.findByText(/Refreshed at:/);
    const copy = container.querySelector(`${ROW_ALPHA} .copy-btn`) as HTMLElement;
    fireEvent.click(copy);
    expect(screen.getByText("Could not copy crew ID alpha. Clipboard access is unavailable.")).toBeInTheDocument();
    expect(container.querySelector(ROW_ALPHA)).not.toHaveClass("selected");
  });
});

describe("detail failure states (6.7)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    window.location.hash = "";
  });

  it("shows an unavailable state, not the fleet's list, when the agents request fails", async () => {
    const fleetAgents = [{ task_id: "fleet-t1", agent: "spectre", done: false, elapsed_secs: 3 }];
    renderWith(
      { [AGENTS_URL]: () => new Response("{}", { status: 500, headers: { "content-type": "application/json" } }) },
      [crew({ crew_id: "alpha", agents: fleetAgents })],
    );
    const { container } = render(<App />);
    await screen.findByText(/Refreshed at:/);
    fireEvent.click(container.querySelector(ROW_ALPHA) as HTMLElement);
    await waitFor(() => expect(screen.getByText("Active tasks unavailable.")).toBeInTheDocument());
    expect(screen.queryByText("fleet-t1")).toBeNull();
    expect(screen.queryByText("No active tasks.")).toBeNull();
  });

  it("shows no scheduled-jobs section and sends no request for one", async () => {
    const { mock } = renderWith();
    const { container } = render(<App />);
    await screen.findByText(/Refreshed at:/);
    fireEvent.click(container.querySelector(ROW_ALPHA) as HTMLElement);
    await screen.findByText("Handoff: TRN-371");
    expect(screen.queryByRole("heading", { name: "Scheduled jobs" })).toBeNull();
    expect(screen.queryByText("Session expired, sign in again")).toBeNull();
    expect(crewProxyCalls(mock)).toHaveLength(0);
    expect(screen.getByText("Credentials")).toBeInTheDocument();
  });

  it("requests live tasks only for a running crew", async () => {
    const { mock } = renderWith({}, [crew({ crew_id: "alpha", status: "stopped" })]);
    const { container } = render(<App />);
    await screen.findByText(/Refreshed at:/);
    fireEvent.click(container.querySelector(ROW_ALPHA) as HTMLElement);
    await screen.findByText("Handoff: TRN-371");
    expect(callsTo(mock, AGENTS_URL)).toHaveLength(0);
    expect(crewProxyCalls(mock)).toHaveLength(0);
    expect(screen.getByText(/Crew is asleep. Live schedule data is unavailable\./)).toBeInTheDocument();
  });
});

describe("a crew that starts while its row is open", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    window.location.hash = "";
  });

  it("requests live tasks once the crew is running, instead of waiting forever", async () => {
    vi.useFakeTimers();
    let status = "stopped";
    const mock = routeFetch({
      [FLEET_URL]: () => jsonResponse(fleet([crew({ crew_id: "alpha", status: status })])),
      [AGENTS_URL]: liveAgents,
      [MAIL_URL]: mailSubjects,
    });
    const { container } = render(<App />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    await act(async () => {
      fireEvent.click(container.querySelector(ROW_ALPHA) as HTMLElement);
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(callsTo(mock, AGENTS_URL)).toHaveLength(0);

    // The crew starts. The next fleet poll reports it running once the 25 s auto-pause has passed.
    status = "running";
    await act(async () => {
      await vi.advanceTimersByTimeAsync(26_000);
    });

    expect(callsTo(mock, AGENTS_URL)).toHaveLength(1);
    expect(screen.queryByText("Loading tasks…")).toBeNull();
    expect(screen.getByText("live-task-1")).toBeInTheDocument();
    expect(crewProxyCalls(mock)).toHaveLength(0);
  });
});
