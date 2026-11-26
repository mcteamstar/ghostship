import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CRITICAL_AFTER_MS, STALE_AFTER_MS, staleLevel, useNow } from "../src/time";

describe("staleLevel", () => {
  const T0 = 1_800_000_000_000;

  it("is null while no fetch is failing, even when the data is old", () => {
    expect(staleLevel(T0 + 60_000, T0, false)).toBeNull();
  });

  it("is null before any fetch has succeeded", () => {
    expect(staleLevel(T0, null, true)).toBeNull();
  });

  it("is null while the data is no more than 15 seconds old", () => {
    expect(staleLevel(T0 + STALE_AFTER_MS, T0, true)).toBeNull();
  });

  it("is stale after 15 seconds of failing fetches", () => {
    expect(staleLevel(T0 + STALE_AFTER_MS + 1, T0, true)).toBe("stale");
    expect(staleLevel(T0 + CRITICAL_AFTER_MS, T0, true)).toBe("stale");
  });

  it("is critical after 30 seconds of failing fetches", () => {
    expect(staleLevel(T0 + CRITICAL_AFTER_MS + 1, T0, true)).toBe("critical");
  });
});

describe("useNow", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("advances once per interval", async () => {
    const { result } = renderHook(() => useNow(1000));
    const start = result.current;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(result.current).toBe(start + 3000);
  });
});
