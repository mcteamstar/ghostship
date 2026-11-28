import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../../src/App";
import { crew, fleet, htmlResponse, jsonResponse, routeFetch } from "../support/fixtures";

const FLEET_URL = "/api/crews";

/** Rows in the order they appear in the table, skipping the divider. */
function rowIds(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll<HTMLTableRowElement>("tr[data-crew-id]")).map(
    (row) => row.dataset.crewId ?? "",
  );
}

/** Only the rows the filter has left visible. */
function visibleRowIds(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll<HTMLTableRowElement>("tr[data-crew-id]"))
    .filter((row) => !row.hidden)
    .map((row) => row.dataset.crewId ?? "");
}

function statusText(): HTMLElement {
  return document.getElementById("status-left") as HTMLElement;
}

describe("fleet page shell (4.1)", () => {
  beforeEach(() => {
    document.title = "Ghostship Fleet Radar";
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("shows the Radar heading with the running count in the page title after a refresh", async () => {
    routeFetch({
      [FLEET_URL]: () =>
        jsonResponse(fleet([
          crew({ crew_id: "alpha", status: "running" }),
          crew({ crew_id: "beta", status: "running" }),
          crew({ crew_id: "gamma", status: "stopped" }),
        ])),
    });
    const { container } = render(<App />);
    expect(screen.getByRole("heading", { name: /Ghostship Radar/ })).toBeInTheDocument();
    await screen.findByText(/Refreshed at:/);
    // The title is set in an effect that runs after the status line renders, so wait for it.
    await waitFor(() => expect(document.title).toBe("Fleet Radar (2 running)"));
    expect(rowIds(container)).toEqual(["alpha", "beta", "gamma"]);
  });

  it("shows the time of the last successful refresh in the status line", async () => {
    routeFetch({ [FLEET_URL]: () => jsonResponse(fleet([crew()])) });
    render(<App />);
    const status = await screen.findByText(/^Refreshed at: /);
    expect(status.textContent).toMatch(/^Refreshed at: \S.+/);
    expect(statusText()).not.toHaveClass("error");
  });

  it("shows a loading state, not an empty fleet, before the first response", () => {
    routeFetch({ [FLEET_URL]: () => new Promise<Response>(() => {}) });
    render(<App />);
    expect(statusText()).toHaveTextContent("Loading…");
    expect(screen.getByText("Fetching fleet data…")).toBeInTheDocument();
    expect(screen.queryByText("No crews registered.")).not.toBeInTheDocument();
  });

  it("shows an error state when the first fetch fails, with the transport message", async () => {
    routeFetch({ [FLEET_URL]: () => new Response("Bad Gateway", { status: 502, headers: { "content-type": "text/html" } }) });
    render(<App />);
    expect(await screen.findByText("Transport unreachable — check ga-transport is running")).toBeInTheDocument();
    expect(statusText()).toHaveClass("error");
    expect(screen.getByText("Could not load the fleet.")).toBeInTheDocument();
  });

  it("keeps the last good data on screen when a later fetch fails, with stale marks at 15 and 30 seconds", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: false });
    let fail = false;
    routeFetch({
      [FLEET_URL]: () => (fail ? new Response("down", { status: 503 }) : jsonResponse(fleet([crew({ crew_id: "alpha" })]))),
    });
    const { container } = render(<App />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(rowIds(container)).toEqual(["alpha"]);

    fail = true;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000); // first failed poll
    });
    expect(statusText()).toHaveClass("error");
    expect(statusText()).not.toHaveClass("stale");
    expect(rowIds(container)).toEqual(["alpha"]);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(11_000); // about 16 s since the last success
    });
    expect(statusText()).toHaveClass("error", "stale");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000); // about 31 s since the last success
    });
    expect(statusText()).toHaveClass("error", "stale-critical");
    expect(statusText()).toHaveTextContent("Transport unreachable");
  });

  it("shows a network message when the browser cannot reach Radar", async () => {
    routeFetch({ [FLEET_URL]: () => { throw new TypeError("Failed to fetch"); } });
    render(<App />);
    expect(await screen.findByText("Network error — check your connection")).toBeInTheDocument();
  });

  it("explains an expired session with a sign-in link, not a parse error", async () => {
    routeFetch({ [FLEET_URL]: () => htmlResponse("<html>Sign in</html>") });
    render(<App />);
    expect(await screen.findByText(/Session expired, sign in again/)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "Sign in" });
    expect(link).toHaveAttribute("href", "/dashboard/login");
    expect(document.body.textContent).not.toMatch(/Unexpected token/);
  });

  it("shows the empty state for a fleet with no crews", async () => {
    routeFetch({ [FLEET_URL]: () => jsonResponse(fleet([])) });
    render(<App />);
    expect(await screen.findByText("No crews registered.")).toBeInTheDocument();
    expect(document.title).toBe("Fleet Radar (0 running)");
  });

  it("shows capacity and free memory in the summary when the fleet reports them", async () => {
    routeFetch({ [FLEET_URL]: () => jsonResponse(fleet([crew()], { active_crews: 2, max_active_crews: 3, host_memory_available_gb: 4.06 })) });
    render(<App />);
    expect(await screen.findByText("2 / 3 crews")).toBeInTheDocument();
    expect(screen.getByText("4.1 GB")).toBeInTheDocument();
  });
});

describe("fleet table ordering and sections (4.2)", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("keeps the filter text and the filtered rows across a fleet refresh", async () => {
    vi.useFakeTimers();
    const many = Array.from({ length: 9 }, (_, i) => crew({ crew_id: `crew-${i}` }));
    routeFetch({ [FLEET_URL]: () => jsonResponse(fleet(many)) });
    const { container } = render(<App />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    const filter = screen.getByRole("textbox", { name: "Filter crews" });
    fireEvent.change(filter, { target: { value: "crew-3" } });
    const before = visibleRowIds(container);
    expect(before).toEqual(["crew-3"]);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000); // a scheduled fleet refresh
    });
    expect(filter).toHaveValue("crew-3");
    expect(visibleRowIds(container)).toEqual(before);
  });

  it("lists running crews first and divides them from the inactive ones", async () => {
    routeFetch({
      [FLEET_URL]: () =>
        jsonResponse(fleet([
          crew({ crew_id: "stopped-one", status: "stopped", created_at: "2026-11-01T00:00:00Z" }),
          crew({ crew_id: "running-one", status: "running", created_at: "2026-11-02T00:00:00Z" }),
        ])),
    });
    const { container } = render(<App />);
    await screen.findByText(/Refreshed at:/);
    const divider = screen.getByRole("heading", { name: "Inactive 1" });
    expect(divider).toHaveTextContent("Inactive");
    expect(divider).not.toHaveAttribute("hidden");
    expect(rowIds(container)).toEqual(["running-one", "stopped-one"]);
  });

  it("hides the Inactive divider when no inactive crew is visible", async () => {
    routeFetch({ [FLEET_URL]: () => jsonResponse(fleet([crew({ crew_id: "only", status: "running" })])) });
    render(<App />);
    await screen.findByText(/Refreshed at:/);
    expect(screen.queryByRole("heading", { name: /Inactive/ })).toBeNull();
  });

  it("orders each section newest created first, with invalid dates last", async () => {
    routeFetch({
      [FLEET_URL]: () =>
        jsonResponse(fleet([
          crew({ crew_id: "old", created_at: "2026-10-01T00:00:00Z" }),
          crew({ crew_id: "broken", created_at: "not-a-date" }),
          crew({ crew_id: "new", created_at: "2026-11-20T00:00:00Z" }),
          crew({ crew_id: "missing", created_at: null }),
          crew({ crew_id: "stopped-new", status: "stopped", created_at: "2026-11-25T00:00:00Z" }),
          crew({ crew_id: "stopped-old", status: "stopped", created_at: "2026-09-01T00:00:00Z" }),
        ])),
    });
    const { container } = render(<App />);
    await screen.findByText(/Refreshed at:/);
    expect(rowIds(container)).toEqual(["new", "old", "broken", "missing", "stopped-new", "stopped-old"]);
  });

  it("sorts each section by last task when the Last Task header is chosen, cycling back to the default", async () => {
    routeFetch({
      [FLEET_URL]: () =>
        jsonResponse(fleet([
          crew({ crew_id: "a", last_task_at: "2026-11-10T00:00:00Z", created_at: "2026-11-01T00:00:00Z" }),
          crew({ crew_id: "b", last_task_at: null, created_at: "2026-11-05T00:00:00Z" }),
          crew({ crew_id: "c", last_task_at: "2026-11-20T00:00:00Z", created_at: "2026-11-02T00:00:00Z" }),
        ])),
    });
    const { container } = render(<App />);
    await screen.findByText(/Refreshed at:/);
    const sortButton = screen.getByRole("button", { name: "Last task" });
    // Default: newest created first (b 11-05, c 11-02, a 11-01).
    expect(rowIds(container)).toEqual(["b", "c", "a"]);

    fireEvent.click(sortButton);
    expect(rowIds(container)).toEqual(["c", "a", "b"]);

    fireEvent.click(sortButton);
    expect(rowIds(container)).toEqual(["a", "c", "b"]);

    fireEvent.click(sortButton);
    expect(rowIds(container)).toEqual(["b", "c", "a"]);
  });

  it("marks a running crew whose gateway is unhealthy and never a stopped one", async () => {
    routeFetch({
      [FLEET_URL]: () =>
        jsonResponse(fleet([
          crew({ crew_id: "healthy", gateway_healthy: true }),
          crew({ crew_id: "sick", gateway_healthy: false }),
          crew({ crew_id: "parked", status: "stopped", gateway_healthy: false }),
        ])),
    });
    const { container } = render(<App />);
    await screen.findByText(/Refreshed at:/);
    const warning = (id: string) => container.querySelector(`tr[data-crew-id="${id}"] .radar-warning`);
    expect(warning("healthy")).toBeNull();
    expect(warning("sick")).toHaveTextContent("Gateway unreachable");
    expect(warning("parked")).toBeNull();
    expect(container.querySelector('tr[data-crew-id="parked"]')).toHaveTextContent("stopped");
  });

  it("shows the captain as active, paused or stale", async () => {
    const hourAgo = new Date(Date.now() - 3_600_000).toISOString();
    routeFetch({
      [FLEET_URL]: () =>
        jsonResponse(fleet([
          crew({ crew_id: "on", captain: { enabled: true, schedule: "every 600s", last_checkin_at: new Date().toISOString() } }),
          crew({ crew_id: "off", captain: { enabled: false, schedule: "every 600s" } }),
          crew({ crew_id: "late", captain: { enabled: true, schedule: "every 600s", last_checkin_at: hourAgo } }),
          crew({ crew_id: "none", captain: null }),
        ])),
    });
    const { container } = render(<App />);
    await screen.findByText(/Refreshed at:/);
    const badge = (id: string) => container.querySelector(`tr[data-crew-id="${id}"] .captain-badge`);
    expect(badge("on")).toHaveTextContent("Captain active");
    expect(badge("on")).not.toHaveClass("captain-stale");
    expect(badge("off")).toHaveTextContent("Captain paused");
    expect(badge("late")).toHaveTextContent("Captain overdue");
    expect(badge("late")).toHaveClass("captain-stale");
    expect(badge("none")).toBeNull();
  });

  it("links a dashboard only when it is an http or https URL", async () => {
    routeFetch({
      [FLEET_URL]: () =>
        jsonResponse(fleet([
          crew({ crew_id: "linked", dashboard_url: "http://localhost:8443/" }),
          crew({ crew_id: "unlinked", dashboard_url: null }),
          crew({ crew_id: "odd", dashboard_url: "javascript:alert(1)" }),
        ])),
    });
    const { container } = render(<App />);
    await screen.findByText(/Refreshed at:/);
    const link = container.querySelector('tr[data-crew-id="linked"] a') as HTMLAnchorElement;
    expect(link).toHaveAttribute("href", "http://localhost:8443/");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(container.querySelector('tr[data-crew-id="odd"] a')).toBeNull();
    expect(container.querySelector('tr[data-crew-id="unlinked"] a')).toBeNull();
  });

  it("shows the count of active agent tasks on the crew", async () => {
    routeFetch({
      [FLEET_URL]: () =>
        jsonResponse(fleet([
          crew({
            crew_id: "busy",
            agents: [
              { task_id: "t1", agent: "ghost", done: false, elapsed_secs: 5 },
              { task_id: "t2", agent: "reaper", done: true, elapsed_secs: 9 },
            ],
          }),
        ])),
    });
    const { container } = render(<App />);
    await screen.findByText(/Refreshed at:/);
    expect(container.querySelector('tr[data-crew-id="busy"] [data-label="Active tasks"]')).toHaveTextContent(/^1$/);
  });

  it("shows the crew filter only above eight crews and narrows rows by crew ID and comp", async () => {
    const many = Array.from({ length: 9 }, (_, i) =>
      crew({ crew_id: `crew-${i}`, comp: i === 0 ? "research" : "spec-ops" }),
    );
    routeFetch({ [FLEET_URL]: () => jsonResponse(fleet(many)) });
    const { container } = render(<App />);
    await screen.findByText(/Refreshed at:/);
    const filter = screen.getByRole("textbox", { name: "Filter crews" });

    fireEvent.change(filter, { target: { value: "RESEARCH" } });
    expect(visibleRowIds(container)).toEqual(["crew-0"]);

    fireEvent.change(filter, { target: { value: "crew-3" } });
    expect(visibleRowIds(container)).toEqual(["crew-3"]);

    fireEvent.change(filter, { target: { value: "nothing-here" } });
    expect(visibleRowIds(container)).toEqual([]);
    expect(screen.getByText("No crews match filter.")).toBeInTheDocument();
    expect(screen.queryByText("No crews registered.")).not.toBeInTheDocument();
  });

  it("shows the crew filter at every fleet size", async () => {
    routeFetch({ [FLEET_URL]: () => jsonResponse(fleet([crew({ crew_id: "a" }), crew({ crew_id: "b" })])) });
    render(<App />);
    await screen.findByText(/Refreshed at:/);
    expect(screen.getByRole("textbox", { name: "Filter crews" })).toBeInTheDocument();
  });
});

describe("crew names in the table", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the crew ID as text, not markup", async () => {
    routeFetch({ [FLEET_URL]: () => jsonResponse(fleet([crew({ crew_id: "alpha" })])) });
    const { container } = render(<App />);
    await screen.findByText(/Refreshed at:/);
    const row = container.querySelector('tr[data-crew-id="alpha"]') as HTMLElement;
    expect(within(row).getByText("alpha", { selector: ".crew-id" })).toBeInTheDocument();
  });
});
