import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "../../src/App";
import { MAILBOX_ORDER } from "../../src/api/types";
import { crew, fleet, jsonResponse, routeFetch } from "../support/fixtures";

afterEach(() => {
  history.replaceState(null, "", location.pathname);
  vi.unstubAllGlobals();
});
it("preserves fleet filters and inspection across presentation modes", async () => {
  routeFetch({
    "/api/crews": () => jsonResponse(fleet([
      crew({ crew_id: "alpha", gateway_healthy: false }),
      crew({ crew_id: "beta", status: "stopped", gateway_healthy: false }),
    ])),
    "/api/crews/alpha/agents": () => jsonResponse({ agents: [] }),
  });
  render(<App />);
  await screen.findByRole("button", { name: "Expand details for alpha" });
  fireEvent.click(screen.getByRole("button", { name: "Needs attention" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Filter crews" }), { target: { value: "alpha" } });
  fireEvent.click(screen.getByRole("button", { name: "Expand details for alpha" }));
  fireEvent.click(screen.getByRole("button", { name: "Cards" }));
  expect(screen.getByRole("textbox", { name: "Filter crews" })).toHaveValue("alpha");
  expect(screen.getByRole("button", { name: "Needs attention" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("heading", { name: "Ghostship Radar", level: 1 })).toBeVisible();
  expect(screen.queryByRole("navigation", { name: "Radar" })).toBeNull();
  const inspector = screen.getByRole("complementary", { name: "Crew details" });
  expect(within(inspector).getByRole("heading", { name: "alpha", level: 2 })).toBeVisible();
  expect(within(inspector).getByRole("region", { name: "Messages" })).toBeVisible();
  expect(within(inspector).getByRole("button", { name: "Messages", pressed: true })).toBeVisible();
  expect(within(inspector).queryByRole("region", { name: "Crew overview" })).toBeNull();
  fireEvent.click(within(inspector).getByRole("button", { name: "Overview" }));
  expect(within(inspector).getByRole("region", { name: "Crew overview" })).toBeVisible();
  expect(within(inspector).queryByRole("region", { name: "Messages" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Expand details for beta" })).toBeNull();
});

it("groups the same retained deliveries by time, sender and recipient", async () => {
  const mailboxes = Object.fromEntries(MAILBOX_ORDER.map(name => [name, name === "ghost" ? [
    { subject: "Older handoff", sender: null, timestamp: null },
    { subject: "Review ready", sender: "raven", timestamp: "2026-11-28T03:00:00Z" },
  ] : []]));
  routeFetch({
    "/api/crews": () => jsonResponse(fleet([crew({ crew_id: "alpha", status: "stopped" })])),
    "/api/crews/alpha/mail-history": () => jsonResponse({ mailboxes, capped: true }),
  });
  render(<App />);
  await screen.findByRole("button", { name: "Expand details for alpha" });
  fireEvent.click(screen.getByRole("button", { name: "Expand details for alpha" }));
  const history = await screen.findByRole("region", { name: "Mailbox history" });
  expect(within(history).getAllByRole("listitem")[0]).toHaveTextContent("Review ready");
  fireEvent.click(within(history).getByRole("button", { name: "Sender" }));
  expect(within(history).getByRole("heading", { name: /unknown sender/i })).toBeVisible();
  fireEvent.click(within(history).getByRole("button", { name: "Recipient" }));
  expect(within(history).getByRole("heading", { name: /ghost.*2/i })).toBeVisible();
  expect(within(history).getByText(/up to 50/)).toBeVisible();
});

it("loads mail when a crew is selected, retries failure, and retains the snapshot", async () => {
  const mailboxes = Object.fromEntries(MAILBOX_ORDER.map(name => [name, []]));
  const historyRead = vi.fn()
    .mockImplementationOnce(() => jsonResponse({}, 502))
    .mockImplementation(() => jsonResponse({ mailboxes, capped: false }));
  routeFetch({
    "/api/crews": () => jsonResponse(fleet([crew({ crew_id: "alpha", status: "stopped" })])),
    "/api/crews/alpha/mail-history": historyRead,
  });
  render(<App />);
  expect(historyRead).not.toHaveBeenCalled();
  fireEvent.click(await screen.findByRole("button", { name: "Expand details for alpha" }));
  fireEvent.click(await screen.findByRole("button", { name: "Retry mailbox history" }));
  fireEvent.click(await screen.findByRole("button", { name: "Recipient" }));
  expect(screen.getByRole("button", { name: "Recipient" })).toHaveAttribute("aria-pressed", "true");
  expect(historyRead).toHaveBeenCalledTimes(2);
});

it("opens cards from their metadata and keeps card actions independent", async () => {
  routeFetch({
    "/api/crews": () => jsonResponse(fleet([
      crew({ crew_id: "alpha", status: "stopped", dashboard_url: "http://localhost:8443/" }),
    ])),
  });
  render(<App />);
  await screen.findByRole("button", { name: "Expand details for alpha" });
  fireEvent.click(screen.getByRole("button", { name: "Cards" }));
  const card = screen.getByRole("listitem");
  const dashboard = within(card).getByRole("link", { name: "Wake and open dashboard" });
  expect(dashboard).toHaveAttribute("href", "http://localhost:8443/");
  dashboard.addEventListener("click", event => event.preventDefault(), { once: true });
  fireEvent.click(dashboard);
  fireEvent.click(within(card).getByRole("button", { name: "Copy crew ID alpha" }));
  expect(screen.queryByRole("complementary", { name: "Crew details" })).toBeNull();

  fireEvent.click(within(card).getByText("spec-ops · kiro"));
  expect(screen.getByRole("complementary", { name: "Crew details" })).toBeVisible();
  expect(within(card).getByRole("button", { name: "Collapse details for alpha" })).toHaveAttribute("aria-expanded", "true");
});
