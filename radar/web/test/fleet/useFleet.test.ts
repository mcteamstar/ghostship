import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RequestError } from "../../src/api/request";
import type { FleetPayload } from "../../src/api/types";
import { AUTO_PAUSE_MS, FLEET_POLL_MS, useFleet } from "../../src/fleet/useFleet";

const fleet = (status = "running"): FleetPayload => ({ crews: [{ crew_id: "alpha", status }] });
const outage = () => new RequestError("transport-unreachable", "HTTP 503", 503);

/** Moves fake time forward and lets the resolved fetch promises run. */
async function advance(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("useFleet", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("has no data until the first fetch succeeds", async () => {
    const fetcher = vi.fn().mockResolvedValue(fleet());
    const { result } = renderHook(() => useFleet(0, fetcher));
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();
    await advance(0);
    expect(result.current.data).toEqual(fleet());
    expect(result.current.lastSuccessAt).toBe(Date.now());
  });

  it("polls every five seconds", async () => {
    const fetcher = vi.fn().mockResolvedValue(fleet());
    renderHook(() => useFleet(0, fetcher));
    await advance(0);
    expect(fetcher).toHaveBeenCalledTimes(1);
    await advance(FLEET_POLL_MS - 1);
    expect(fetcher).toHaveBeenCalledTimes(1);
    await advance(1);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("keeps the last good payload when a later poll fails, and reports the failure", async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(fleet("running")).mockRejectedValueOnce(outage());
    const { result } = renderHook(() => useFleet(0, fetcher));
    await advance(0);
    await advance(FLEET_POLL_MS);
    expect(result.current.data).toEqual(fleet("running"));
    expect(result.current.error?.kind).toBe("transport-unreachable");
  });

  it("clears the error once a poll succeeds again", async () => {
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce(outage())
      .mockResolvedValueOnce(fleet("stopped"));
    const { result } = renderHook(() => useFleet(0, fetcher));
    await advance(0);
    expect(result.current.error).not.toBeNull();
    await advance(FLEET_POLL_MS);
    expect(result.current.error).toBeNull();
    expect(result.current.data).toEqual(fleet("stopped"));
  });

  it("skips scheduled polls while a detail is open and the last success is under 25 seconds old", async () => {
    const fetcher = vi.fn().mockResolvedValue(fleet());
    renderHook(({ open }) => useFleet(open, fetcher), { initialProps: { open: 1 } });
    await advance(0);
    expect(fetcher).toHaveBeenCalledTimes(1);
    await advance(20_000); // the 5, 10, 15 and 20 second ticks are all paused
    expect(fetcher).toHaveBeenCalledTimes(1);
    await advance(5_000); // the 25 second tick is the first one at the pause limit
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(AUTO_PAUSE_MS).toBe(25_000);
  });

  it("polls on the normal schedule when no detail is open", async () => {
    const fetcher = vi.fn().mockResolvedValue(fleet());
    renderHook(({ open }) => useFleet(open, fetcher), { initialProps: { open: 0 } });
    await advance(0);
    await advance(FLEET_POLL_MS * 2);
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it("resumes the normal schedule when the last detail closes", async () => {
    const fetcher = vi.fn().mockResolvedValue(fleet());
    const { rerender } = renderHook(({ open }) => useFleet(open, fetcher), { initialProps: { open: 1 } });
    await advance(0);
    await advance(20_000);
    expect(fetcher).toHaveBeenCalledTimes(1);
    rerender({ open: 0 });
    await advance(FLEET_POLL_MS);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("never starts a second poll while one is still in flight", async () => {
    const fetcher = vi.fn().mockImplementation(() => new Promise<FleetPayload>(() => {}));
    renderHook(() => useFleet(0, fetcher));
    await advance(FLEET_POLL_MS * 4);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("stops polling once unmounted", async () => {
    const fetcher = vi.fn().mockResolvedValue(fleet());
    const { unmount } = renderHook(() => useFleet(0, fetcher));
    await advance(0);
    unmount();
    await advance(FLEET_POLL_MS * 3);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
