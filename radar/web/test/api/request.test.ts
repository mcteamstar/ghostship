import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  REQUEST_TIMEOUT_MS,
  RequestError,
  getJson,
  isRequestErrorOfKind,
  toRequestError,
} from "../../src/api/request";

/** A fetch Response with the given status and body. */
function jsonResponse(body: unknown, status = 200, contentType = "application/json"): Response {
  return new Response(typeof body === "string" ? body : JSON.stringify(body), {
    status,
    headers: { "content-type": contentType },
  });
}

/** An opaque redirect, as fetch(redirect: "manual") returns for a 3xx. */
function opaqueRedirect(): Response {
  return {
    type: "opaqueredirect",
    status: 0,
    ok: false,
    redirected: false,
    headers: new Headers(),
    json: () => Promise.reject(new SyntaxError("opaque redirect has no body")),
  } as unknown as Response;
}

async function failureOf(promise: Promise<unknown>): Promise<RequestError> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof RequestError) return error;
    throw error;
  }
  throw new Error("expected the request to fail");
}

describe("getJson: classification of a response", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the parsed body for a good JSON response", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ crews: [] }));
    await expect(getJson("/api/crews")).resolves.toEqual({ crews: [] });
  });

  it("sends the session cookie and never follows a redirect", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));
    await getJson("/api/crews");
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/crews");
    expect(options.credentials).toBe("include");
    expect(options.redirect).toBe("manual");
  });

  it("reports an opaque redirect to the login page as an expired session", async () => {
    fetchMock.mockResolvedValue(opaqueRedirect());
    const error = await failureOf(getJson("/api/crews"));
    expect(error.kind).toBe("session-expired");
  });

  it("reports a followed redirect as an expired session", async () => {
    const followed = jsonResponse({ ok: true });
    Object.defineProperty(followed, "redirected", { value: true });
    fetchMock.mockResolvedValue(followed);
    expect((await failureOf(getJson("/api/crews"))).kind).toBe("session-expired");
  });

  it("reports a 200 login page (non-JSON body) as an expired session, not a parse error", async () => {
    fetchMock.mockResolvedValue(
      new Response("<!DOCTYPE html><title>Sign in</title>", {
        status: 200,
        headers: { "content-type": "text/html; charset=utf-8" },
      }),
    );
    const error = await failureOf(getJson("/api/crews"));
    expect(error.kind).toBe("session-expired");
    expect(error.message).not.toMatch(/Unexpected token/);
  });

  it.each([502, 503, 504])("reports HTTP %i as the transport being unreachable", async (status) => {
    fetchMock.mockResolvedValue(new Response("Bad Gateway", { status, headers: { "content-type": "text/html" } }));
    const error = await failureOf(getJson("/api/crews"));
    expect(error.kind).toBe("transport-unreachable");
    expect(error.status).toBe(status);
  });

  it.each([403, 404, 500])("reports HTTP %i as an HTTP error that names the status", async (status) => {
    fetchMock.mockResolvedValue(jsonResponse({ error: "x" }, status));
    const error = await failureOf(getJson("/api/crews"));
    expect(error.kind).toBe("http-error");
    expect(error.status).toBe(status);
    expect(error.message).toBe(`HTTP ${status}`);
  });

  it("reports a JSON content type with an unparseable body as an HTTP error", async () => {
    fetchMock.mockResolvedValue(new Response("{not json", { status: 200, headers: { "content-type": "application/json" } }));
    const error = await failureOf(getJson("/api/crews"));
    expect(error.kind).toBe("http-error");
    expect(error.message).toBe("Unexpected response body");
  });

  it("reports a thrown network error as a network failure", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const error = await failureOf(getJson("/api/crews"));
    expect(error.kind).toBe("network");
    expect(error.message).toBe("Failed to fetch");
  });

  it("times out a request that never answers", async () => {
    vi.useFakeTimers();
    try {
      fetchMock.mockImplementation(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
          }),
      );
      const pending = failureOf(getJson("/api/crews"));
      await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS + 1);
      const error = await pending;
      expect(error.kind).toBe("network");
      expect(error.message).toBe("Request timed out");
    } finally {
      vi.useRealTimers();
    }
  });

  it("rethrows a cancel by the caller unchanged, so the caller can drop it", async () => {
    const controller = new AbortController();
    fetchMock.mockImplementation(
      (_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        }),
    );
    const pending = getJson("/api/crews", { signal: controller.signal });
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    await expect(pending).rejects.not.toBeInstanceOf(RequestError);
  });
});

describe("error helpers", () => {
  it("recognises a RequestError by kind", () => {
    expect(isRequestErrorOfKind(new RequestError("network", "x"), "network")).toBe(true);
    expect(isRequestErrorOfKind(new RequestError("network", "x"), "session-expired")).toBe(false);
    expect(isRequestErrorOfKind(new Error("x"), "network")).toBe(false);
  });

  it("maps a stray exception to an HTTP error rather than a network error", () => {
    const mapped = toRequestError(new Error("bug"));
    expect(mapped.kind).toBe("http-error");
    expect(mapped.message).toBe("bug");
  });

  it("returns an existing RequestError unchanged", () => {
    const original = new RequestError("transport-unreachable", "HTTP 503", 503);
    expect(toRequestError(original)).toBe(original);
  });
});
