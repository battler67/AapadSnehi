import { afterEach, describe, expect, it, vi } from "vitest";
import { compactNumber, timeAgo, titleCase } from "./format";

describe("presentation formatters", () => {
  afterEach(() => vi.useRealTimers());

  it("formats incident age against a stable operating time", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-21T12:00:00Z"));

    expect(timeAgo("2026-08-21T10:00:00Z")).toBe("2h ago");
    expect(timeAgo("2026-08-19T12:00:00Z")).toBe("2 days ago");
  });

  it("formats operational labels and Indian compact numbers", () => {
    expect(titleCase("coverage_gap")).toBe("Coverage Gap");
    expect(compactNumber(18_500)).toMatch(/18\.5K|18\.5k/);
  });
});
