import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  agentsUrl,
  fetchAgents,
  fetchFleet,
  fetchMailSubjects,
  mailSubjectsUrl,
  refreshAuthUrl,
} from "../../src/api/endpoints";
import { RequestError } from "../../src/api/request";
import { isFleetPayload, isMailSubjectsPayload } from "../../src/api/guards";
import { MAILBOX_ORDER } from "../../src/api/types";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function fullMailboxes(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  const mailboxes: Record<string, unknown> = {};
  for (const name of MAILBOX_ORDER) mailboxes[name] = [];
  return { ...mailboxes, ...overrides };
}

describe("endpoint URLs", () => {
  it("encodes the crew id in every per-crew path", () => {
    expect(agentsUrl("we ird/id")).toBe("/api/crews/we%20ird%2Fid/agents");
    expect(mailSubjectsUrl("alpha")).toBe("/api/crews/alpha/mail-subjects");
    expect(refreshAuthUrl("alpha")).toBe("/api/crews/alpha/auth/refresh");
  });
});

describe("payload guards", () => {
  it("accepts a fleet payload whose crews all carry an id and status", () => {
    expect(isFleetPayload({ crews: [{ crew_id: "alpha", status: "running" }] })).toBe(true);
    expect(isFleetPayload({ crews: [] })).toBe(true);
  });

  it("rejects a fleet payload without a crews list or with a crew missing its id", () => {
    expect(isFleetPayload({})).toBe(false);
    expect(isFleetPayload({ crews: {} })).toBe(false);
    expect(isFleetPayload({ crews: [{ status: "running" }] })).toBe(false);
  });

  it("requires all eight mailboxes as lists of strings", () => {
    expect(isMailSubjectsPayload({ mailboxes: fullMailboxes({ ghost: ["hi"] }) })).toBe(true);
    const missing = fullMailboxes();
    delete missing.captain;
    expect(isMailSubjectsPayload({ mailboxes: missing })).toBe(false);
    expect(isMailSubjectsPayload({ mailboxes: fullMailboxes({ ghost: [42] }) })).toBe(false);
    expect(isMailSubjectsPayload({ mailboxes: fullMailboxes({ ghost: "hi" }) })).toBe(false);
    expect(isMailSubjectsPayload({ error: "x" })).toBe(false);
  });
});

describe("typed fetchers", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the fleet when the payload has the expected shape", async () => {
    fetchMock.mockResolvedValue(json({ crews: [{ crew_id: "alpha", status: "running" }] }));
    const fleet = await fetchFleet();
    expect(fleet.crews[0]?.crew_id).toBe("alpha");
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/crews");
  });

  it("fails a fleet response of the wrong shape instead of showing it as empty", async () => {
    fetchMock.mockResolvedValue(json({ message: "maintenance" }));
    const error = await fetchFleet().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(RequestError);
    expect((error as RequestError).kind).toBe("http-error");
    expect((error as RequestError).message).toBe("Unexpected fleet response");
  });

  it("fails agents of the wrong shape instead of showing them as empty", async () => {
    fetchMock.mockResolvedValueOnce(json({ tasks: [] }));
    await expect(fetchAgents("alpha")).rejects.toThrow("Unexpected agents response");
  });

  it("fails a partial mailbox payload rather than showing partial data", async () => {
    const partial = fullMailboxes();
    delete partial.admiral;
    fetchMock.mockResolvedValue(json({ mailboxes: partial }));
    await expect(fetchMailSubjects("alpha")).rejects.toThrow("Unexpected mailbox response");
  });

  it("passes a caller's cancel signal to the request", async () => {
    fetchMock.mockResolvedValue(json({ agents: [] }));
    const controller = new AbortController();
    await fetchAgents("alpha", { signal: controller.signal });
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init.signal).toBeDefined();
  });
});
