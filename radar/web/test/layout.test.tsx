import { render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/App";
import { crew, fleet, jsonResponse, routeFetch } from "./support/fixtures";

const css = readFileSync(resolve("src/styles/radar.css"), "utf-8");

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("narrow layout (6.4)", () => {
  it("switches the fleet table to stacked cards below 640 px", () => {
    expect(css).toContain("@media (max-width: 639px)");
    expect(css).toContain("#fleet-table tr.data-row");
    expect(css).toMatch(/td\[data-label\]::before\s*\{\s*content: attr\(data-label\)/);
  });

  it("labels every cell with its column name for the cards", async () => {
    routeFetch({ "/api/crews": () => jsonResponse(fleet([crew({ crew_id: "alpha" })])) });
    const { container } = render(<App />);
    await screen.findByText(/Refreshed at:/);
    const labels = Array.from(container.querySelectorAll<HTMLElement>('tr[data-crew-id="alpha"] td[data-label]')).map(
      (cell) => cell.dataset.label,
    );
    expect(labels).toEqual(["Status", "Active tasks", "Last task"]);
  });

  it("keeps the crew name, status and expand control on every card", async () => {
    routeFetch({ "/api/crews": () => jsonResponse(fleet([crew({ crew_id: "alpha" })])) });
    const { container } = render(<App />);
    await screen.findByText(/Refreshed at:/);
    const row = container.querySelector('tr[data-crew-id="alpha"]') as HTMLElement;
    expect(row.querySelector(".crew-id")).toHaveTextContent("alpha");
    expect(row.querySelector(".expand-btn")).toBeInTheDocument();
    expect(row.querySelector(".badge")).toHaveTextContent("running");
  });
});
