import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import { RequestError } from "../../src/api/request";
import { StatusBar } from "../../src/components/StatusBar";

it("keeps the last successful timestamp visible outside error announcements", () => {
  const error = new RequestError("network", "offline");
  const { rerender } = render(<StatusBar fleet={{ data: null, error, lastSuccessAt: null }} />);
  expect(screen.queryByText(/Refreshed at/)).toBeNull();
  for (const [age, label] of [[20_000, "Stale."], [35_000, "Critically stale."]] as const) {
    rerender(<StatusBar fleet={{ data: null, error, lastSuccessAt: Date.now() - age }} />);
    expect(screen.getByText(/Refreshed at/)).toBeVisible();
    expect(within(screen.getByRole("status")).getByText(label)).toBeVisible();
    expect(within(screen.getByRole("status")).queryByText(/Refreshed at/)).toBeNull();
  }
  rerender(<StatusBar fleet={{ data: null, error: null, lastSuccessAt: Date.now() }} />);
  expect(screen.getByRole("status")).toBeEmptyDOMElement();
});
