import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../../src/App";
import { crew, fleet, jsonResponse, routeFetch } from "../support/fixtures";

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = "";
});

describe("accessibility (6.8)", () => {
  it("has no axe violations with a fleet, an open detail and a refresh notice on screen", async () => {
    routeFetch({
      "/api/crews": () =>
        jsonResponse(fleet(
          [
            crew({
              crew_id: "alpha",
              captain: { enabled: true, schedule: "every 600s", last_checkin_at: new Date().toISOString() },
              agents: [{ task_id: "t1", agent: "ghost", done: false, elapsed_secs: 3 }],
            }),
            crew({ crew_id: "beta", status: "stopped", dashboard_url: "http://localhost:8443/" }),
          ],
          { active_crews: 1, max_active_crews: 3, host_memory_available_gb: 4.1 },
        )),
      "/api/crews/alpha/agents": () => jsonResponse({ agents: [{ task_id: "t1", agent: "ghost", done: false, elapsed_secs: 3 }] }),
      "/api/crews/alpha/auth/refresh": () => jsonResponse({ status: "current" }),
    });
    const { container } = render(<App />);
    await screen.findByText(/Refreshed at:/);
    fireEvent.click(container.querySelector('tr[data-crew-id="alpha"]') as HTMLElement);
    fireEvent.click(screen.getByRole("button", { name: "Overview" }));
    fireEvent.click(screen.getByRole("button", { name: "Refresh auth" }));
    await waitFor(() => expect(screen.getByText("Already current.")).toBeInTheDocument());
    for (const name of ["Active tasks", "Captain", "Credentials"]) {
      expect(screen.getByRole("heading", { name, level: 2 })).toBeInTheDocument();
    }

    const results = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(results.violations.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
  }, 30_000);

  it("names every control, exposes expansion and sort state, and announces refresh errors", async () => {
    routeFetch({
      "/api/crews": () => jsonResponse(fleet([crew({ crew_id: "alpha" })])),
    });
    const { container } = render(<App />);
    await screen.findByText(/Refreshed at:/);
    const expand = container.querySelector('tr[data-crew-id="alpha"] .expand-btn') as HTMLElement;
    expect(expand).toHaveAttribute("aria-expanded", "false");
    expect(expand).toHaveAttribute("aria-label", "Expand details for alpha");
    expect(screen.getByRole("button", { name: "Copy crew ID alpha" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Filter crews" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Sort" })).toHaveValue("");
    expect(document.getElementById("status-left")).toHaveAttribute("aria-live", "polite");
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
    fireEvent.change(screen.getByRole("combobox", { name: "Sort" }), { target: { value: "desc" } });
    expect(screen.getByRole("combobox", { name: "Sort" })).toHaveValue("desc");
  });
});
