// Port of tests/unit/test_radar_auth_refresh_client.py (TRN-367). Each assertion of that
// Python suite has a counterpart here, checked against the rendered React tree and the
// request the browser sends. Polls run on fake timers, so the "survives a poll" cases use
// the same five-second fleet refresh the browser does.
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { App } from "../../src/App";
import { REFRESH_OUTCOMES, type RefreshStatus } from "../../src/auth/refresh";
import { crew, callsTo, fleet, htmlResponse, jsonResponse, opaqueRedirect, routeFetch } from "../support/fixtures";

const FLEET_URL = "/api/crews";
const REFRESH_URL = "/api/crews/alpha/auth/refresh";
const SENTINEL = "SENTINEL-SHOULD-NOT-RENDER";

type Reply = () => Response | Promise<Response>;

function outcome(status: string, message?: string): Reply {
  return () => jsonResponse(message === undefined ? { status } : { status, message });
}

/** Routes the fleet, every listed crew's detail endpoints, and each crew's refresh endpoint. */
function setup(refresh: Reply, crews = [crew({ crew_id: "alpha" })]): Mock {
  const routes: Record<string, Reply> = { [FLEET_URL]: () => jsonResponse(fleet(crews)) };
  for (const c of crews) {
    const id = encodeURIComponent(c.crew_id);
    routes[`/api/crews/${id}/agents`] = () => jsonResponse({ agents: [] });
    routes[`/crews/${id}/api/crons`] = () => jsonResponse({ jobs: [] });
    routes[`/api/crews/${id}/mail-subjects`] = () => jsonResponse({ mailboxes: {} });
    routes[`/api/crews/${id}/auth/refresh`] = c.crew_id === "alpha" ? refresh : outcome("refreshed");
  }
  return routeFetch(routes);
}

/** The summary row for a crew, found by its data attribute (IDs may hold quotes). */
function rowFor(container: HTMLElement, crewId: string): HTMLElement {
  const row = Array.from(container.querySelectorAll<HTMLElement>("tr[data-crew-id]")).find(
    (candidate) => candidate.dataset.crewId === crewId,
  );
  if (!row) throw new Error(`no row for ${crewId}`);
  return row;
}

/** Renders the page and opens the crew's row, so its Credentials section is on screen. */
async function openRow(crewId = "alpha"): Promise<HTMLElement> {
  const { container } = render(<App />);
  await screen.findByText(/Refreshed at:/);
  fireEvent.click(rowFor(container, crewId));
  await waitFor(() => expect(screen.getByText("Credentials")).toBeInTheDocument());
  return container;
}

function refreshButton(container: HTMLElement, crewId = "alpha"): HTMLButtonElement {
  const button = Array.from(container.querySelectorAll<HTMLButtonElement>("button[data-auth-refresh]")).find(
    (candidate) => candidate.dataset.authRefresh === crewId,
  );
  if (!button) throw new Error(`no refresh button for ${crewId}`);
  return button;
}

function resultNode(container: HTMLElement): HTMLElement | null {
  return container.querySelector(".auth-refresh-result");
}

/** The text of the notice, with its heading and guidance joined. */
function noticeText(container: HTMLElement): string {
  return resultNode(container)?.textContent ?? "";
}

/** A promise that the test settles by hand, so a request can be left in flight. */
function deferred(): { promise: Promise<Response>; settle: (response: Response) => void } {
  let settle!: (response: Response) => void;
  const promise = new Promise<Response>((resolve) => {
    settle = resolve;
  });
  return { promise, settle };
}

/** Lets pending promise callbacks run. */
const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

describe("Refresh auth (TRN-367 client port)", () => {
  beforeEach(() => {
    window.location.hash = "";
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    window.location.hash = "";
  });

  describe("request", () => {
    it("posts to the refresh endpoint with session credentials and a manual redirect", async () => {
      const mock = setup(outcome("refreshed"));
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(noticeText(container)).toContain("Refreshed."));
      const calls = callsTo(mock, REFRESH_URL);
      expect(calls).toHaveLength(1);
      const { signal, ...shape } = calls[0] as RequestInit & { signal?: AbortSignal };
      expect(shape).toEqual({ method: "POST", credentials: "include", redirect: "manual" });
      expect(signal).toBeInstanceOf(AbortSignal);
    });

    it("sends no body, headers, mode or referrer; the abort signal is the only addition", async () => {
      const mock = setup(outcome("refreshed"));
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(noticeText(container)).toContain("Refreshed."));
      const [init] = callsTo(mock, REFRESH_URL);
      expect(Object.keys(init ?? {}).sort()).toEqual(["credentials", "method", "redirect", "signal"]);
    });

    it("URL-encodes the crew ID in the request path", async () => {
      const crews = [crew({ crew_id: "we ird" })];
      const mock = setup(outcome("refreshed"), crews);
      // The refresh route for this crew is the generic one; the path is what is under test.
      const container = await openRow("we ird");
      fireEvent.click(refreshButton(container, "we ird"));
      await waitFor(() => expect(callsTo(mock, "/api/crews/we%20ird/auth/refresh")).toHaveLength(1));
    });
  });

  describe("outcomes", () => {
    it.each(Object.keys(REFRESH_OUTCOMES) as RefreshStatus[])(
      "shows the %s outcome with its own label, tone and the transport guidance",
      async (status) => {
        setup(outcome(status, `guidance for ${status}`));
        const container = await openRow();
        fireEvent.click(refreshButton(container));
        await waitFor(() => expect(resultNode(container)).not.toBeNull());
        const { label, tone } = REFRESH_OUTCOMES[status];
        const node = resultNode(container) as HTMLElement;
        expect(node.querySelector("strong")).toHaveTextContent(label);
        expect(node).toHaveClass(`auth-${tone}`);
        expect(node).toHaveTextContent(`guidance for ${status}`);
        for (const [other, definition] of Object.entries(REFRESH_OUTCOMES)) {
          if (other !== status) expect(node.textContent).not.toContain(definition.label);
        }
      },
    );

    it.each(Object.keys(REFRESH_OUTCOMES) as RefreshStatus[])(
      "falls back to the default guidance for %s when the response has none",
      async (status) => {
        setup(() => jsonResponse({ status }));
        const container = await openRow();
        fireEvent.click(refreshButton(container));
        await waitFor(() => expect(resultNode(container)).not.toBeNull());
        expect(noticeText(container)).toContain(REFRESH_OUTCOMES[status].text);
        expect(noticeText(container)).not.toMatch(/undefined/);
        if (status === "recreate_required") expect(noticeText(container)).toContain("docs/auth.md");
      },
    );

    it.each([null, "", 7, { a: 1 }, ["x"]])("treats the non-text message %j as no guidance", async (message) => {
      setup(() => jsonResponse({ status: "refreshed", message }));
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(resultNode(container)).not.toBeNull());
      expect(noticeText(container)).toContain(REFRESH_OUTCOMES.refreshed.text);
      expect(noticeText(container)).not.toContain("[object Object]");
    });

    it("shows hostile guidance as text, not markup", async () => {
      const hostile = `<img src=x onerror=alert(1)> & <script>alert(2)</script> "quoted"`;
      setup(outcome("refresh_failed", hostile));
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(resultNode(container)).not.toBeNull());
      expect(container.querySelector(".auth-refresh-result img")).toBeNull();
      expect(container.querySelector(".auth-refresh-result script")).toBeNull();
      expect(noticeText(container)).toContain(hostile);
    });

    it("takes the label and tone from the fixed table, never from the response", async () => {
      setup(() => jsonResponse({ status: "refreshed", message: "ok", label: "Hacked.", tone: "error", className: "auth-error" }));
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(resultNode(container)).not.toBeNull());
      const node = resultNode(container) as HTMLElement;
      expect(node).toHaveClass("auth-ok");
      expect(node).not.toHaveClass("auth-error");
      expect(node.textContent).toContain("Refreshed.");
      expect(node.textContent).not.toContain("Hacked.");
    });

    it("draws only the status and the message from the response", async () => {
      setup(() =>
        jsonResponse({
          status: "refreshed",
          message: "ok",
          crew_id: "alpha",
          backend: "kiro",
          profile: "default",
          token: SENTINEL,
          payload: SENTINEL,
          credential: SENTINEL,
          authorization: SENTINEL,
        }),
      );
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(resultNode(container)).not.toBeNull());
      expect(container.innerHTML).not.toContain(SENTINEL);
    });

    it.each(["constructor", "__proto__", "toString", "hasOwnProperty", "<b>x</b>", "", "REFRESHED", 7, null])(
      "treats the status %j as an unknown result, never an outcome",
      async (status) => {
        setup(() => jsonResponse({ status, message: "should not be shown" }));
        const container = await openRow();
        fireEvent.click(refreshButton(container));
        await waitFor(() => expect(resultNode(container)).not.toBeNull());
        expect(noticeText(container)).toContain("Refresh result unknown.");
        expect(noticeText(container)).not.toContain("should not be shown");
        expect(container.querySelector(".auth-refresh-result b")).toBeNull();
        for (const definition of Object.values(REFRESH_OUTCOMES)) {
          expect(noticeText(container)).not.toContain(definition.label);
        }
      },
    );

    it.each([null, "refreshed", 3, [], ["refreshed"]])("treats the body %j as an unknown result", async (body) => {
      setup(() => jsonResponse(body));
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(resultNode(container)).not.toBeNull());
      expect(noticeText(container)).toContain("Refresh result unknown.");
    });

    it("treats a JSON content type with an unparseable body as an unknown result", async () => {
      setup(() => new Response("{not json", { status: 200, headers: { "content-type": "application/json" } }));
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(resultNode(container)).not.toBeNull());
      expect(noticeText(container)).toContain("Refresh result unknown.");
    });
  });

  describe("session expiry", () => {
    const expectExpired = (container: HTMLElement) => {
      const node = resultNode(container) as HTMLElement;
      expect(node.querySelector("strong")).toHaveTextContent("Session expired.");
      const link = node.querySelector("a") as HTMLAnchorElement;
      expect(link).toHaveAttribute("href", "/dashboard/login");
      expect(link).toHaveTextContent("Sign in again");
      for (const definition of Object.values(REFRESH_OUTCOMES)) {
        expect(node.textContent).not.toContain(definition.label);
      }
      expect(node.textContent).not.toContain("did not complete");
    };

    it("shows an opaque redirect to the login page as session expired", async () => {
      const mock = setup(() => opaqueRedirect());
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(resultNode(container)).not.toBeNull());
      expectExpired(container);
      expect(callsTo(mock, REFRESH_URL)[0]?.redirect).toBe("manual");
    });

    it("shows a followed redirect as session expired", async () => {
      setup(() => {
        const followed = htmlResponse("<html>login</html>");
        Object.defineProperty(followed, "redirected", { value: true });
        return followed;
      });
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(resultNode(container)).not.toBeNull());
      expectExpired(container);
    });

    it("shows a 200 login page served in place of the API as session expired", async () => {
      setup(() => htmlResponse("<html>Sign in</html>"));
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(resultNode(container)).not.toBeNull());
      expectExpired(container);
    });

    it("does not trust a JSON outcome that arrived after a redirect", async () => {
      setup(() => {
        const followed = jsonResponse({ status: "refreshed", message: "ok" });
        Object.defineProperty(followed, "redirected", { value: true });
        return followed;
      });
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(resultNode(container)).not.toBeNull());
      expectExpired(container);
    });

    it("keeps the session-expired notice across a fleet poll and leaves the button usable", async () => {
      vi.useFakeTimers();
      setup(() => opaqueRedirect());
      const { container } = render(<App />);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      await act(async () => {
        fireEvent.click(rowFor(container, "alpha"));
        await vi.advanceTimersByTimeAsync(0);
      });
      await act(async () => {
        fireEvent.click(refreshButton(container));
        await vi.advanceTimersByTimeAsync(0);
      });
      expectExpired(container);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(25_000);
      });
      expectExpired(container);
      expect(refreshButton(container)).not.toBeDisabled();
    });
  });

  describe("failures", () => {
    const didNotComplete = (container: HTMLElement): string => {
      const node = resultNode(container) as HTMLElement;
      expect(node.querySelector("strong")).toHaveTextContent("Refresh did not complete.");
      expect(node.textContent).not.toContain("Session expired");
      for (const definition of Object.values(REFRESH_OUTCOMES)) {
        expect(node.textContent).not.toContain(definition.label);
      }
      return node.textContent ?? "";
    };

    it.each([502, 503, 504])("reports HTTP %i as the transport being unreachable", async (status) => {
      setup(() => new Response(JSON.stringify({ error: "transport unreachable", detail: SENTINEL }), {
        status,
        headers: { "content-type": "application/json" },
      }));
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(resultNode(container)).not.toBeNull());
      expect(didNotComplete(container)).toContain("could not get a result from ga-transport");
      expect(container.innerHTML).not.toContain(SENTINEL);
    });

    it("reports a 403 as a same-origin rejection", async () => {
      setup(() => new Response("{}", { status: 403, headers: { "content-type": "application/json" } }));
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(resultNode(container)).not.toBeNull());
      expect(didNotComplete(container)).toContain("same-origin check");
    });

    it.each([404, 500])("reports HTTP %i with the status code", async (status) => {
      setup(() => new Response("{}", { status, headers: { "content-type": "application/json" } }));
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(resultNode(container)).not.toBeNull());
      expect(didNotComplete(container)).toContain(`HTTP ${status}`);
    });

    it("does not mistake an HTML error page from a proxy for an expired session", async () => {
      setup(() => new Response("<html>Bad Gateway</html>", { status: 502, headers: { "content-type": "text/html" } }));
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(resultNode(container)).not.toBeNull());
      expect(didNotComplete(container)).toContain("could not get a result from ga-transport");
    });

    it("reports a network failure and releases the button", async () => {
      setup(() => {
        throw new TypeError("Failed to fetch");
      });
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(resultNode(container)).not.toBeNull());
      expect(didNotComplete(container)).toContain("Network error.");
      expect(refreshButton(container)).not.toBeDisabled();
    });

    it("releases the button when fetch throws synchronously", async () => {
      const routed = setup(outcome("current"));
      vi.stubGlobal("fetch", (url: string, init: RequestInit) => {
        if (url === REFRESH_URL) throw new Error("boom");
        return routed(url, init);
      });
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(resultNode(container)).not.toBeNull());
      expect(didNotComplete(container)).toContain("Network error.");
      expect(refreshButton(container)).not.toBeDisabled();
    });

    it("can be retried after a failure", async () => {
      let calls = 0;
      setup(() => {
        calls += 1;
        return calls === 1 ? new Response("{}", { status: 502 }) : jsonResponse({ status: "current" });
      });
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(resultNode(container)).toHaveTextContent("Refresh did not complete."));
      expect(refreshButton(container)).not.toBeDisabled();
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(noticeText(container)).toContain("Already current."));
    });
  });

  describe("one request at a time", () => {
    it("sends nothing on a second click while a request is in flight", async () => {
      const held = deferred();
      const mock = setup(() => held.promise);
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      fireEvent.click(refreshButton(container));
      expect(callsTo(mock, REFRESH_URL)).toHaveLength(1);
      held.settle(jsonResponse({ status: "refreshed" }));
      await waitFor(() => expect(noticeText(container)).toContain("Refreshed."));
    });

    it("draws the button disabled, busy and labelled while in flight", async () => {
      const held = deferred();
      setup(() => held.promise);
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      const button = refreshButton(container);
      expect(button).toBeDisabled();
      expect(button).toHaveAttribute("aria-busy", "true");
      expect(button).toHaveTextContent("Refreshing…");
      held.settle(jsonResponse({ status: "refreshed" }));
      await waitFor(() => expect(refreshButton(container)).not.toBeDisabled());
    });

    it("re-enables the button when the request finishes, and a new request is then allowed", async () => {
      const mock = setup(outcome("current"));
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(noticeText(container)).toContain("Already current."));
      expect(refreshButton(container)).not.toBeDisabled();
      expect(refreshButton(container)).not.toHaveAttribute("aria-busy");
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(callsTo(mock, REFRESH_URL)).toHaveLength(2));
    });

    it("does not block another crew's refresh", async () => {
      const held = deferred();
      const crews = [crew({ crew_id: "alpha" }), crew({ crew_id: "bravo" })];
      const mock = setup(() => held.promise, crews);
      const container = await openRow();
      fireEvent.click(rowFor(container, "bravo"));
      await waitFor(() => expect(refreshButton(container, "bravo")).toBeInTheDocument());
      fireEvent.click(refreshButton(container));
      fireEvent.click(refreshButton(container, "bravo"));
      expect(callsTo(mock, REFRESH_URL)).toHaveLength(1);
      expect(callsTo(mock, "/api/crews/bravo/auth/refresh")).toHaveLength(1);
      held.settle(jsonResponse({ status: "refreshed" }));
      await waitFor(() => expect(refreshButton(container)).not.toBeDisabled());
    });

    it("clears the previous outcome when a new request starts", async () => {
      const held = deferred();
      let calls = 0;
      setup(() => {
        calls += 1;
        return calls === 1 ? jsonResponse({ status: "refreshed" }) : held.promise;
      });
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(noticeText(container)).toContain("Refreshed."));
      fireEvent.click(refreshButton(container));
      expect(resultNode(container)).toBeNull();
      held.settle(jsonResponse({ status: "current" }));
      await waitFor(() => expect(noticeText(container)).toContain("Already current."));
    });
  });

  describe("state survives the fleet poll", () => {
    it("keeps the busy state and the outcome through a poll, with no refetch or resubmit", async () => {
      vi.useFakeTimers();
      const held = deferred();
      const mock = setup(() => held.promise);
      const { container } = render(<App />);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      await act(async () => {
        fireEvent.click(rowFor(container, "alpha"));
        await vi.advanceTimersByTimeAsync(0);
      });
      await act(async () => {
        fireEvent.click(refreshButton(container));
        await vi.advanceTimersByTimeAsync(0);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(25_000); // a fleet refresh redraws the table
      });
      expect(refreshButton(container)).toBeDisabled();
      expect(refreshButton(container)).toHaveTextContent("Refreshing…");
      expect(callsTo(mock, REFRESH_URL)).toHaveLength(1);

      await act(async () => {
        held.settle(jsonResponse({ status: "pending_on_wake", message: "waits" }));
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(noticeText(container)).toContain("Pending until wake.");
      await act(async () => {
        await vi.advanceTimersByTimeAsync(25_000);
      });
      expect(noticeText(container)).toContain("Pending until wake.");
      expect(callsTo(mock, REFRESH_URL)).toHaveLength(1);
    });

    it("drops the outcome when the row is collapsed and reopened", async () => {
      setup(outcome("refreshed"));
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(noticeText(container)).toContain("Refreshed."));
      fireEvent.click(rowFor(container, "alpha"));
      fireEvent.click(rowFor(container, "alpha"));
      await waitFor(() => expect(screen.getByText("Credentials")).toBeInTheDocument());
      expect(resultNode(container)).toBeNull();
      expect(refreshButton(container)).not.toBeDisabled();
    });

    it("shows a reopened row's button disabled while its request is still in flight", async () => {
      const held = deferred();
      setup(() => held.promise);
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      fireEvent.click(rowFor(container, "alpha")); // close
      fireEvent.click(rowFor(container, "alpha")); // reopen
      await waitFor(() => expect(screen.getByText("Credentials")).toBeInTheDocument());
      expect(refreshButton(container)).toBeDisabled();
      await act(async () => {
        held.settle(jsonResponse({ status: "refreshed" }));
        await flush();
      });
    });

    it("discards a result that arrives after the row was collapsed", async () => {
      const held = deferred();
      setup(() => held.promise);
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      fireEvent.click(rowFor(container, "alpha")); // close while in flight
      await act(async () => {
        held.settle(jsonResponse({ status: "refreshed" }));
        await flush();
      });
      fireEvent.click(rowFor(container, "alpha")); // reopen
      await waitFor(() => expect(screen.getByText("Credentials")).toBeInTheDocument());
      expect(resultNode(container)).toBeNull();
      expect(refreshButton(container)).not.toBeDisabled();
    });
  });

  describe("panel markup", () => {
    it.each(["running", "stopped"] as const)("gives a %s crew a Credentials section with the button", async (status) => {
      setup(outcome("current"), [crew({ crew_id: "alpha", status })]);
      const container = await openRow();
      expect(screen.getByText("Credentials")).toBeInTheDocument();
      expect(refreshButton(container)).toHaveTextContent("Refresh auth");
      expect(refreshButton(container)).not.toBeDisabled();
    });

    it("renders the button as a non-submitting button", async () => {
      setup(outcome("current"));
      const container = await openRow();
      expect(refreshButton(container)).toHaveAttribute("type", "button");
    });

    it("escapes the crew ID in the attribute", async () => {
      const hostile = 'a"><img src=x onerror=1>';
      setup(outcome("current"), [crew({ crew_id: hostile })]);
      const container = await openRow(hostile);
      expect(container.querySelector("img")).toBeNull();
      expect(refreshButton(container, hostile)).toHaveAttribute("data-auth-refresh", hostile);
    });

    it("shows no result before any refresh", async () => {
      setup(outcome("current"));
      const container = await openRow();
      expect(resultNode(container)).toBeNull();
    });

    it("holds no credential or transport secret names in the markup", async () => {
      setup(outcome("refreshed"));
      const container = await openRow();
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(resultNode(container)).not.toBeNull());
      for (const forbidden of ["Authorization", "Bearer", "X-Transport-Token", "gs_session", "api-key", "password"]) {
        expect(container.innerHTML).not.toContain(forbidden);
      }
    });
  });

  describe("click wiring", () => {
    it("starts exactly one refresh for a click on the button, and none for the rest of the panel", async () => {
      const mock = setup(outcome("current"));
      const container = await openRow();
      fireEvent.click(screen.getByText("Credentials"));
      fireEvent.click(screen.getByText("No active tasks."));
      expect(callsTo(mock, REFRESH_URL)).toHaveLength(0);
      fireEvent.click(refreshButton(container));
      await waitFor(() => expect(noticeText(container)).toContain("Already current."));
      expect(callsTo(mock, REFRESH_URL)).toHaveLength(1);
    });

    it("never sends a refresh on its own, however many fleet polls run", async () => {
      vi.useFakeTimers();
      const mock = setup(outcome("current"));
      const { container } = render(<App />);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      await act(async () => {
        fireEvent.click(rowFor(container, "alpha"));
        await vi.advanceTimersByTimeAsync(0);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(60_000);
      });
      expect(callsTo(mock, REFRESH_URL)).toHaveLength(0);
    });
  });

  describe("timeout and slow requests", () => {
    const TIMEOUT_TEXT =
      "Refresh did not complete: no answer after 75 seconds. It may still finish; check the crew and retry.";

    /** Renders the page on fake timers and opens the crew's row. */
    async function openRowOnFakeTimers(): Promise<HTMLElement> {
      vi.useFakeTimers();
      const { container } = render(<App />);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      await act(async () => {
        fireEvent.click(rowFor(container, "alpha"));
        await vi.advanceTimersByTimeAsync(0);
      });
      return container;
    }

    async function clickRefresh(container: HTMLElement): Promise<void> {
      await act(async () => {
        fireEvent.click(refreshButton(container));
        await vi.advanceTimersByTimeAsync(0);
      });
    }

    it("shows a still-working note only after 10 seconds in flight", async () => {
      const held = deferred();
      setup(() => held.promise);
      const container = await openRowOnFakeTimers();
      await clickRefresh(container);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(9_999);
      });
      expect(container.querySelector(".auth-refresh-note")).toBeNull();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1);
      });
      expect(container.querySelector(".auth-refresh-note")).toHaveTextContent("Still working…");
      expect(refreshButton(container)).toBeDisabled();
      await act(async () => {
        held.settle(jsonResponse({ status: "current" }));
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(container.querySelector(".auth-refresh-note")).toBeNull();
    });

    it("aborts at 75 seconds, shows the timeout notice, and re-enables the button", async () => {
      const held = deferred();
      const mock = setup(() => held.promise);
      const container = await openRowOnFakeTimers();
      await clickRefresh(container);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(74_999);
      });
      expect(refreshButton(container)).toBeDisabled();
      expect(noticeText(container)).toBe("");
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1);
      });
      const [init] = callsTo(mock, REFRESH_URL);
      expect((init as RequestInit).signal?.aborted).toBe(true);
      expect(noticeText(container)).toBe(TIMEOUT_TEXT);
      expect(resultNode(container)).toHaveClass("auth-warn");
      expect(refreshButton(container)).not.toBeDisabled();
      expect(refreshButton(container)).not.toHaveAttribute("aria-busy");
      expect(container.querySelector(".auth-refresh-note")).toBeNull();
    });

    it("never presents the timeout as a fixed outcome", async () => {
      setup(() => new Promise<Response>(() => undefined));
      const container = await openRowOnFakeTimers();
      await clickRefresh(container);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(75_000);
      });
      const text = noticeText(container);
      for (const definition of Object.values(REFRESH_OUTCOMES)) {
        expect(text).not.toContain(definition.label);
      }
      expect(text).not.toContain("Session expired");
      expect(resultNode(container)).not.toHaveClass("auth-ok");
      expect(resultNode(container)).not.toHaveClass("auth-info");
    });

    it("ignores an answer that arrives after the timeout", async () => {
      const held = deferred();
      setup(() => held.promise);
      const container = await openRowOnFakeTimers();
      await clickRefresh(container);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(75_000);
      });
      await act(async () => {
        held.settle(jsonResponse({ status: "refreshed", message: "late" }));
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(noticeText(container)).toBe(TIMEOUT_TEXT);
      expect(noticeText(container)).not.toContain("Refreshed.");
      expect(refreshButton(container)).not.toBeDisabled();
    });

    it("sends a new request after a timeout", async () => {
      const held = deferred();
      let calls = 0;
      const mock = setup(() => {
        calls += 1;
        return calls === 1 ? held.promise : jsonResponse({ status: "current" });
      });
      const container = await openRowOnFakeTimers();
      await clickRefresh(container);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(75_000);
      });
      await clickRefresh(container);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(callsTo(mock, REFRESH_URL)).toHaveLength(2);
      expect(noticeText(container)).toContain("Already current.");
    });
  });

  describe("styles", () => {
    it("defines every class the action uses", async () => {
      // npm test runs from the package root, so the stylesheet path is relative to it.
      const { readFileSync } = await import("node:fs");
      const { resolve } = await import("node:path");
      const css = readFileSync(resolve("src/styles/radar.css"), "utf-8");
      for (const selector of [
        ".auth-refresh", ".auth-refresh-btn", ".auth-refresh-btn:disabled", ".auth-refresh-result",
        ".auth-ok", ".auth-info", ".auth-warn", ".auth-error",
      ]) {
        expect(css).toContain(selector);
      }
    });
  });
});
