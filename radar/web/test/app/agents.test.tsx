import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../../src/App";
import { personaOf } from "../../src/components/detail/AgentsSection";
import { crew, fleet, jsonResponse, opaqueRedirect, routeFetch } from "../support/fixtures";

const ROW = 'tr[data-crew-id="alpha"]';

function task(id: string, agent: string, done: boolean, elapsed = 30) {
  return { task_id: id, agent, done, elapsed_secs: elapsed };
}

/** Routes the fleet and alpha's live task list, then opens alpha. */
async function openWithTasks(agents: () => Response | Promise<Response>): Promise<HTMLElement> {
  routeFetch({
    "/api/crews": () => jsonResponse(fleet([crew({ crew_id: "alpha" })])),
    "/api/crews/alpha/agents": agents,
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

describe("agent tasks as cards (6.5)", () => {
  it("shows running tasks as cards under their count, and finished tasks behind a count", async () => {
    const running = [task("run-1", "ghost", false), task("run-2", "spectre", false)];
    const finished = Array.from({ length: 11 }, (_, i) => task(`fin-${i}`, "reaper", true));
    const container = await openWithTasks(() => jsonResponse({ agents: [...running, ...finished] }));
    await waitFor(() => expect(screen.getByText("Running · 2")).toBeInTheDocument());
    expect(screen.getByText("Finished · 11")).toBeInTheDocument();
    expect(container.querySelectorAll(".agent-group .agent-cards > li")).toHaveLength(2);
  });

  it("keeps finished tasks in the page behind a closed disclosure", async () => {
    const finished = Array.from({ length: 11 }, (_, i) => task(`fin-${i}`, "reaper", true));
    const container = await openWithTasks(() => jsonResponse({ agents: finished }));
    await waitFor(() => expect(screen.getByText("Finished · 11")).toBeInTheDocument());
    const disclosure = container.querySelector("details.agent-finished") as HTMLDetailsElement;
    expect(disclosure).not.toHaveAttribute("open");
    expect(disclosure.querySelectorAll("li")).toHaveLength(11);
  });

  it("colours the six known personas and gives any other agent a neutral card", async () => {
    const container = await openWithTasks(() =>
      jsonResponse({ agents: [task("t-1", "ghost", false), task("t-2", "Custom-Agent", false), task("t-3", "", false)] }),
    );
    await waitFor(() => expect(screen.getByText("Running · 3")).toBeInTheDocument());
    const cards = Array.from(container.querySelectorAll<HTMLElement>(".agent-cards > li"));
    expect(cards[0]).toHaveClass("persona-ghost");
    expect(cards[1]).toHaveClass("agent-card-unknown");
    expect(cards[1]).toHaveTextContent("Custom-Agent");
    expect(cards[2]).toHaveClass("agent-card-unknown");
    expect(cards[2]).toHaveTextContent("unknown agent");
    expect(personaOf("Raven")).toBe("raven");
    expect(personaOf("captain")).toBeNull();
  });

  it("labels an empty agent name as an unknown agent and still lists the task", async () => {
    await openWithTasks(() => jsonResponse({ agents: [task("t-9", "", false, 12)] }));
    await waitFor(() => expect(screen.getByText("unknown agent")).toBeInTheDocument());
    expect(screen.getByText("12s")).toBeInTheDocument();
  });

  it("shows No active tasks. as the empty state of the running group", async () => {
    await openWithTasks(() => jsonResponse({ agents: [task("f-1", "ghost", true)] }));
    await waitFor(() => expect(screen.getByText("No active tasks.")).toBeInTheDocument());
    expect(screen.getByText("Running · 0")).toBeInTheDocument();
    expect(screen.getByText("Finished · 1")).toBeInTheDocument();
  });

  it("shows each task's agent, short ID, done state and elapsed time", async () => {
    await openWithTasks(() =>
      jsonResponse({ agents: [task("abc123-long-identifier", "ghost", false, 45), task("def456", "raven", true, 0)] }),
    );
    await waitFor(() => expect(screen.getByText("abc123-long-")).toBeInTheDocument());
    const running = document.querySelector(".agent-cards > li") as HTMLElement;
    expect(running).toHaveTextContent("ghost");
    expect(running).toHaveTextContent("running");
    expect(running).toHaveTextContent("45s");
    expect(screen.getByText("def456")).toBeInTheDocument();
  });

  it("shows an unavailable state, not an empty list, when the agents request fails", async () => {
    await openWithTasks(() => new Response("{}", { status: 500, headers: { "content-type": "application/json" } }));
    await waitFor(() => expect(screen.getByText("Active tasks unavailable.")).toBeInTheDocument());
    expect(screen.queryByText("No active tasks.")).toBeNull();
  });

  it("shows the session-expired note when the agents request is redirected to sign-in", async () => {
    await openWithTasks(() => opaqueRedirect());
    await waitFor(() => expect(screen.getByText("Session expired, sign in again")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/dashboard/login");
  });

  it("shows a loading state until the agents request answers", async () => {
    await openWithTasks(() => new Promise<Response>(() => {}));
    expect(screen.getByText("Loading tasks…")).toBeInTheDocument();
  });
});
