import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../../src/App";
import { crew, fleet, jsonResponse, routeFetch } from "../support/fixtures";

afterEach(() => {
  vi.unstubAllGlobals();
});

async function renderFleet(payload: ReturnType<typeof fleet>) {
  routeFetch({ "/api/crews": () => jsonResponse(payload) });
  const view = render(<App />);
  await screen.findByText(/Refreshed at:/);
  return view;
}

function summaryValue(label: string): string | null {
  const item = Array.from(document.querySelectorAll(".summary-item")).find(
    (candidate) => candidate.querySelector("dt")?.textContent === label,
  );
  return item?.querySelector("dd")?.textContent ?? null;
}

describe("fleet summary (6.2)", () => {
  it("combines the running count and maximum, with separate stopped count and free memory", async () => {
    await renderFleet(
      fleet(
        [crew({ crew_id: "a" }), crew({ crew_id: "b" }), crew({ crew_id: "c", status: "stopped" })],
        { active_crews: 2, max_active_crews: 3, host_memory_available_gb: 4.06 },
      ),
    );
    expect(summaryValue("Running")).toBeNull();
    expect(summaryValue("Asleep")).toBe("1");
    expect(summaryValue("Capacity")).toBeNull();
    expect(summaryValue("Active")).toBe("2 / 3");
    expect(summaryValue("Free memory")).toBe("4.1 GB");
  });

  it("omits capacity when the fleet does not report the maximum, with no placeholder number", async () => {
    await renderFleet(fleet([crew()], { active_crews: null, max_active_crews: null }));
    expect(summaryValue("Capacity")).toBeNull();
    expect(screen.queryByText("Capacity")).toBeNull();
    expect(summaryValue("Active")).toBe("1");
  });

  it("omits free memory when the fleet does not report it", async () => {
    await renderFleet(fleet([crew()], { host_memory_available_gb: null }));
    expect(summaryValue("Free memory")).toBeNull();
    expect(screen.queryByText("Free memory")).toBeNull();
  });
});
