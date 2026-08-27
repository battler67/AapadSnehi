import { afterEach, describe, expect, it, vi } from "vitest";
import { API_BASE, api } from "./api";


describe("Bluesky scan API", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("runs the demo adapter with a POST request", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          query: "floods in india",
          scannedCount: 1,
          matchCount: 0,
          authors: [],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    await api.scanBlueskyAuthors("floods in india");

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0][0]).toBe(`${API_BASE}/api/bluesky/scan`);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      method: "POST",
      body: JSON.stringify({ query: "floods in india" }),
      headers: expect.not.objectContaining({ Authorization: expect.anything() }),
    });
  });
});
