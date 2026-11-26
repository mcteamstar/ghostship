import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../../src/App";
import { crew, fleet, jsonResponse, routeFetch } from "../support/fixtures";

afterEach(() => {
  vi.unstubAllGlobals();
});

function visibleIds(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll<HTMLElement>("tr[data-crew-id]"))
    .filter((row) => !row.hidden)
    .map((row) => row.dataset.crewId ?? "");
}

describe("crew filter (6.3)", () => {
  it("is visible for a three-crew fleet", async () => {
    routeFetch({
      "/api/crews": () =>
        jsonResponse(fleet([crew({ crew_id: "alpha" }), crew({ crew_id: "beta" }), crew({ crew_id: "gamma" })])),
    });
    render(<App />);
    await screen.findByText(/Refreshed at:/);
    expect(screen.getByRole("textbox", { name: "Filter crews" })).toBeVisible();
  });

  it("keeps the rows that match the crew ID or comp, ignoring case", async () => {
    routeFetch({
      "/api/crews": () =>
        jsonResponse(fleet([
          crew({ crew_id: "alpha" }),
          crew({ crew_id: "beta", comp: "Research" }),
          crew({ crew_id: "gamma" }),
        ])),
    });
    const { container } = render(<App />);
    await screen.findByText(/Refreshed at:/);
    const filter = screen.getByRole("textbox", { name: "Filter crews" });
    fireEvent.change(filter, { target: { value: "BETA" } });
    expect(visibleIds(container)).toEqual(["beta"]);
    fireEvent.change(filter, { target: { value: "research" } });
    expect(visibleIds(container)).toEqual(["beta"]);
  });

  it("says no crews match when nothing matches, and not that the fleet is empty", async () => {
    routeFetch({ "/api/crews": () => jsonResponse(fleet([crew({ crew_id: "alpha" })])) });
    const { container } = render(<App />);
    await screen.findByText(/Refreshed at:/);
    fireEvent.change(screen.getByRole("textbox", { name: "Filter crews" }), { target: { value: "zzz" } });
    expect(visibleIds(container)).toEqual([]);
    expect(screen.getByText("No crews match filter.")).toBeInTheDocument();
    expect(screen.queryByText("No crews registered.")).toBeNull();
  });
});
